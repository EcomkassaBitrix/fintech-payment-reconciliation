import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from ecomkassa_client import company_cash_register, get_receipt_atol
import amocrm_crm
import bitrix_crm
import alfabank_api
import yookassa_api
import tochka_acquiring_api
import moyklass_crm
import realtycalendar_crm
import payment_verify

SCHEMA = 't_p83864310_fintech_payment_reco'

# Задержка следующей попытки (минуты) по номеру попытки; после последней - статус failed.
# Пауза перед повтором (мин): 1, 5, 15 - после 4-й неудачной попытки задание уходит в «Не удалось».
RETRY_DELAYS = [1, 5, 15]


def _payment(cur, payment_id: str) -> Optional[Dict[str, Any]]:
    cur.execute(f'''
        SELECT wp.id, wp.payment_id, wp.order_id, wp.amount, wp.status, wp.customer_email, wp.customer_phone,
               wp.payment_provider, wp.receipt_id, wp.created_at, wp.integration_id, p.slug, wp.raw_data
        FROM {SCHEMA}.webhook_payments wp
        JOIN {SCHEMA}.user_integrations ui ON ui.id = wp.integration_id
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE wp.id = %s
    ''', (payment_id,))
    r = cur.fetchone()
    if not r:
        return None
    return {
        'id': r[0], 'payment_id': r[1], 'order_id': r[2], 'amount': float(r[3] or 0),
        'status': r[4], 'customer_email': r[5], 'customer_phone': r[6],
        'payment_provider': r[7], 'receipt_id': r[8], 'created_at': r[9].isoformat() if r[9] else None,
        'integration_id': r[10], 'provider_slug': r[11],
        'raw': (r[12] if isinstance(r[12], dict) else json.loads(r[12] or '{}')) if r[11] in ('moyklass', 'realtycalendar', 'alfabank', 'yookassa', 'cloudpayments') else None
    }


def _cart(cur, integration_id: int, provider_payment_id: str) -> Optional[Dict[str, Any]]:
    cur.execute(f'''
        SELECT items, receipt, items_total, source, fiscal_data, fiscalized, receipt_id FROM {SCHEMA}.payment_carts
        WHERE integration_id = %s AND payment_id = %s
    ''', (integration_id, provider_payment_id))
    r = cur.fetchone()
    if not r:
        return None
    return {'items': r[0] or [], 'receipt': r[1] or {}, 'items_total': float(r[2] or 0), 'source': r[3],
            'fiscal': r[4] or {}, 'fiscalized': bool(r[5]), 'receipt_id': r[6]}


def _fetch_alfabank_cart(cur, company_id: int, payment: Dict[str, Any]) -> Optional[str]:
    '''Запрос заказа с корзиной у Альфа-Банка (getOrderStatusExtended) и сохранение корзины.'''
    cur.execute(f'SELECT config FROM {SCHEMA}.user_integrations WHERE id = %s', (payment['integration_id'],))
    row = cur.fetchone()
    config = row[0] if row and isinstance(row[0], dict) else json.loads((row or [None])[0] or '{}')
    order, err = alfabank_api.get_order_status(config, str(payment['payment_id']), payment.get('order_id'), timeout=8)
    if not order:
        return err
    alfabank_api.save_cart(cur, payment['integration_id'], company_id, str(payment['payment_id']), order)
    return None


def _alfabank_single_item(cur, payment: Dict[str, Any], data: Dict[str, Any],
                          scenario: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''
    Заказ Альфа-Банка без корзины: чек одной позицией на сумму платежа,
    название - описание заказа (orderDescription), иначе «Оплата заказа N».
    '''
    raw = payment.get('raw') or {}
    order = raw.get('order') if isinstance(raw.get('order'), dict) else {}
    if not order.get('orderDescription'):
        cur.execute(f'''SELECT raw_data FROM {SCHEMA}.webhook_payments WHERE id = %s''', (payment['id'],))
        row = cur.fetchone()
        fresh = (row[0] if row and isinstance(row[0], dict) else json.loads((row or [None])[0] or '{}')) or {}
        order = fresh.get('order') if isinstance(fresh.get('order'), dict) else order
    description = ' '.join(str(order.get('orderDescription') or '').split())
    order_no = payment.get('order_id') or order.get('orderNumber') or payment['payment_id']
    name = (description or f'Оплата заказа {order_no}')[:128]
    amount = round(float(payment['amount'] or 0), 2)
    if amount <= 0:
        return 'error', data, 'У платежа Альфа-Банка нулевая сумма - чек не пробиваем'
    data['items'] = [{'name': name, 'price': amount, 'quantity': 1, 'amount': amount,
                      'payment_method': 'full_payment', 'payment_object': 'service',
                      'tax': (scenario.get('template') or {}).get('vat') or 'none'}]
    data['items_source'] = 'Альфа-Банк (описание заказа)'
    source = 'описание заказа' if description else 'описания нет, взят номер заказа'
    return 'ready', data, (
        f"Корзины в заказе Альфа-Банка нет - чек одной позицией «{name}» на {amount:.2f} ₽ "
        f"({source}, платёж #{payment['payment_id']})"
    )


def _template_vat_mapping(mapping: Dict[str, Any], scenario: Dict[str, Any], default_mode: str) -> Dict[str, Any]:
    '''
    Ставка НДС из шаблона действия (если задана) - для позиций, у которых нет своей ставки
    из CRM: «Одной позицией» и «Фиксированный». Режим «Товары из CRM» берёт ставку сценария.
    '''
    vat = (scenario.get('template') or {}).get('vat')
    if vat and (mapping.get('items_mode') or default_mode) != 'products':
        return {**mapping, 'vat': vat}
    return mapping


def _fetch_tochka_cart(cur, company_id: int, payment: Dict[str, Any]) -> Optional[str]:
    '''Операция с корзиной у Точки (Get Payment Operation Info) и сохранение корзины.'''
    cur.execute(f'SELECT config FROM {SCHEMA}.user_integrations WHERE id = %s', (payment['integration_id'],))
    row = cur.fetchone()
    config = row[0] if row and isinstance(row[0], dict) else json.loads((row or [None])[0] or '{}')
    token, token_err = tochka_acquiring_api.api_token(cur, company_id, config or {})
    op, err = tochka_acquiring_api.get_operation(token, token_err, str(payment['payment_id']), timeout=8)
    if not op:
        return err
    tochka_acquiring_api.save_cart(cur, payment['integration_id'], company_id, str(payment['payment_id']), op)
    return None


def _fetch_yookassa_cart(cur, company_id: int, payment: Dict[str, Any]) -> Optional[str]:
    '''Чеки платежа в ЮKassa (GET /v3/receipts?payment_id=) -> корзина. Чеков нет - пустая корзина.'''
    config = _integration_config(cur, payment['integration_id'])
    receipts, err = yookassa_api.fetch_receipts(config, str(payment['payment_id']))
    if receipts is None:
        return err
    raw = payment.get('raw') or {}
    pay = raw.get('payment') if isinstance(raw.get('payment'), dict) else {'id': payment['payment_id']}
    yookassa_api.save_cart(cur, payment['integration_id'], company_id, {**pay, 'id': str(payment['payment_id'])}, receipts)
    return None


def _yookassa_single_item(payment: Dict[str, Any], data: Dict[str, Any],
                          scenario: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''Платёж ЮKassa без чека в ЮKassa: одна позиция на сумму платежа, название - описание платежа.'''
    raw = payment.get('raw') or {}
    pay = raw.get('payment') if isinstance(raw.get('payment'), dict) else {}
    refund = raw.get('refund') if isinstance(raw.get('refund'), dict) else {}
    description = ' '.join(str(refund.get('description') or pay.get('description') or '').split())
    order_no = payment.get('order_id') or payment['payment_id']
    name = (description or f'Оплата заказа {order_no}')[:128]
    amount = round(float(payment['amount'] or 0), 2)
    if amount <= 0:
        return 'error', data, 'У платежа ЮKassa нулевая сумма - чек не пробиваем'
    data['items'] = [{'name': name, 'price': amount, 'quantity': 1, 'amount': amount,
                      'payment_method': 'full_payment', 'payment_object': 'service',
                      'tax': (scenario.get('template') or {}).get('vat') or 'none'}]
    data['items_source'] = 'ЮKassa (описание платежа)'
    source = 'описание платежа' if description else 'описания нет, взят номер заказа'
    return 'ready', data, (
        f"Чека в ЮKassa нет - чек одной позицией «{name}» на {amount:.2f} ₽ "
        f"({source}, платёж {payment['payment_id']}). Почта покупателя - из шаблона действия"
    )


def _cloudpayments_single_item(payment: Dict[str, Any], data: Dict[str, Any],
                               scenario: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''Платёж CloudPayments без чека в Data: одна позиция на сумму, название - назначение платежа.'''
    raw = payment.get('raw') or {}
    note = raw.get('notification') if isinstance(raw.get('notification'), dict) else {}
    tx = raw.get('transaction') if isinstance(raw.get('transaction'), dict) else {}
    description = ' '.join(str(note.get('Description') or tx.get('Description') or '').split())
    order_no = payment.get('order_id') or payment['payment_id']
    name = (description or f'Оплата заказа {order_no}')[:128]
    amount = round(float(payment['amount'] or 0), 2)
    if amount <= 0:
        return 'error', data, 'У платежа CloudPayments нулевая сумма - чек не пробиваем'
    data['items'] = [{'name': name, 'price': amount, 'quantity': 1, 'amount': amount,
                      'payment_method': 'full_payment', 'payment_object': 'service',
                      'tax': (scenario.get('template') or {}).get('vat') or 'none'}]
    data['items_source'] = 'CloudPayments (назначение платежа)'
    source = 'назначение платежа' if description else 'назначения нет, взят номер заказа'
    return 'ready', data, (
        f"Состава чека в платеже CloudPayments нет - чек одной позицией «{name}» на {amount:.2f} ₽ "
        f"({source}, транзакция {payment['payment_id']})"
    )


# Провайдеры, у которых корзина приходит в уведомлении и без неё чек не собрать.
CART_FROM_PROVIDER = {'tbank': 'Т-Банк', 'alfabank': 'Альфа-Банк', 'tochka_acquiring': 'Точка', 'yookassa': 'ЮKassa',
                      'cloudpayments': 'CloudPayments'}


def _gateway_integration(cur, company_id: int) -> Optional[int]:
    cur.execute(f'''
        SELECT ui.id FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug IN ('ecomkassa_gateway', 'ecomkassa') AND ui.status = 'active'
        ORDER BY (p.slug = 'ecomkassa_gateway') DESC, ui.id LIMIT 1
    ''', (company_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _prepare_pending_invoice(cur, job: Dict[str, Any], scenario: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any], str]]:
    '''
    Счёт Екомкассы завис в «ожидает оплату». Проверяем оплату в эквайринге по номеру заказа (= UUID счёта).
    Оплачен - заводим у нас оплаченный платёж шлюза и дальше задание идёт как обычное расхождение
    (чек по корзине счёта). Не оплачен - пропуск (перепроверим позже). Нет ответа - повтор.
    None - задание переведено на платёж, продолжаем обычную подготовку.
    '''
    payload = job.get('payload') or {}
    uid = str(payload.get('invoice_uuid') or job['source_id'])
    info = {'invoice_uuid': uid}
    cur.execute(f'''
        SELECT EXISTS (SELECT 1 FROM {SCHEMA}.ecomkassa_receipts
                       WHERE company_id = %s AND order_id = %s AND status = 'done' AND removed_at IS NULL)
    ''', (job['company_id'], uid))
    if cur.fetchone()[0]:
        return 'skipped', info, f'По счёту {uid} в Екомкассе уже есть пробитый чек - коррекция не нужна'
    mapping = scenario.get('field_mapping') or {}
    if mapping.get('verify_mode') == 'none':
        where = 'Без проверки'
        verdict, message, paid = 'paid', f'счёт {uid} в «ожидает оплату», оплату не проверяли', {'system': 'Екомкасса (без проверки)'}
    elif mapping.get('verify_mode') == 'bank':
        where = 'Проверка в банке'
        verdict, message, paid = payment_verify.verify_bank(cur, job['company_id'], [uid, payload.get('external_id')], [])
    else:
        where = 'Проверка в платёжной системе'
        ids = [int(i) for i in (mapping.get('verify_integration_ids') or []) if str(i).isdigit()]
        verdict, message, paid = payment_verify.verify_order(cur, job['company_id'], uid, ids or None)
    if verdict == 'not_paid':
        return 'skipped', info, f'{where}: {message} - чек не нужен, перепроверим позже'
    if verdict != 'paid':
        return 'error', info, f'{where}: {message}'
    integration_id = _gateway_integration(cur, job['company_id'])
    if not integration_id:
        return 'error', info, 'Нет активной интеграции Екомкассы, к которой привязать платёж'
    amount = float(paid.get('amount') or payload.get('amount') or 0)
    try:
        paid_at = datetime.fromisoformat(str(payload.get('updated')).replace('Z', '+00:00'))
        paid_at = paid_at.astimezone(timezone.utc).replace(tzinfo=None) if paid_at.tzinfo else paid_at
    except (TypeError, ValueError):
        paid_at = None
    cur.execute(f'''
        INSERT INTO {SCHEMA}.webhook_payments (integration_id, company_id, payment_id, amount, order_id, status,
                                               raw_data, payment_provider, origin, created_at)
        VALUES (%s, %s, %s, %s, %s, 'CONFIRMED', %s, %s, 'automation',
                COALESCE(%s, NOW()))
        ON CONFLICT (integration_id, payment_id, status) DO UPDATE SET
            amount = CASE WHEN {SCHEMA}.webhook_payments.amount = 0 THEN EXCLUDED.amount ELSE {SCHEMA}.webhook_payments.amount END
        RETURNING id
    ''', (integration_id, job['company_id'], uid, amount, uid,
          json.dumps({'source': 'verify', 'invoice_uuid': uid, 'verified': paid}, ensure_ascii=False),
          paid.get('system'), paid_at))
    row_id = cur.fetchone()[0]
    cur.execute(f'''
        UPDATE {SCHEMA}.automation_jobs SET source_type = 'payment', source_id = %s,
               payload = payload || %s::jsonb, updated_at = NOW()
        WHERE id = %s AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.automation_jobs
                                      WHERE scenario_id = %s AND source_type = 'payment' AND source_id = %s)
        RETURNING id
    ''', (str(row_id), json.dumps({'reason': 'discrepancy', 'webhook_payment_id': row_id,
                                     'verified_by': paid.get('system')}, ensure_ascii=False),
          job['id'], job['scenario_id'], str(row_id)))
    if not cur.fetchone():
        return 'skipped', info, f'По платежу счёта {uid} уже есть другое задание сценария'
    log(cur, job['id'], 'info', f'{where}: {message}. Платёж отмечен у нас как оплаченный')
    job.update({'source_type': 'payment', 'source_id': str(row_id), 'verified': True,
                'payload': {**payload, 'reason': 'discrepancy', 'webhook_payment_id': row_id}})
    return None


def prepare(cur, job: Dict[str, Any], scenario: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''
    Сбор данных для действия сценария. Возвращает (статус, данные, сообщение в журнал):
    ready - всё собрано; skipped - действие не нужно; error - повторить позже.
    Корзина берётся у того же провайдера, откуда пришёл платёж.
    '''
    if job['source_type'] in ('crm_deal', 'crm_lead'):
        return prepare_crm(cur, job, scenario)
    if job['source_type'] == 'ecom_invoice':
        converted = _prepare_pending_invoice(cur, job, scenario)
        if converted:
            return converted
    if job['source_type'] != 'payment':
        return 'error', {}, f"Источник «{job['source_type']}» пока не поддерживается"

    payment = _payment(cur, job['source_id'])
    if not payment:
        return 'error', {}, 'Платёж не найден в базе'
    rk_refund = payment['provider_slug'] == 'realtycalendar' and payment['status'] == 'REFUNDED'
    chosen = (scenario.get('field_mapping') or {}).get('payment_statuses')
    chosen = [str(x) for x in chosen] if isinstance(chosen, list) else []
    if chosen and payment['status'] not in chosen:
        return 'skipped', {'payment': payment}, f"Платёж в статусе {payment['status']} - сценарий настроен на другие статусы"
    if not chosen and payment['status'] not in ('CONFIRMED', 'AUTHORIZED', 'done', 'OFFSET') and not rk_refund:
        return 'skipped', {'payment': payment}, f"Платёж в статусе {payment['status']} - документ не нужен"
    if chosen:
        # Один сценарий - один документ на платёж: «удержан» и «оплачен» одного платежа второй чек не пробьют.
        cur.execute(f'''
            SELECT wp2.status FROM {SCHEMA}.automation_documents d
            JOIN {SCHEMA}.webhook_payments wp2 ON wp2.id = d.payment_row_id
            WHERE d.scenario_id = %s AND d.job_id <> %s AND d.status <> 'fail'
              AND wp2.integration_id = %s AND wp2.payment_id = %s
            LIMIT 1
        ''', (scenario['id'], job['id'], payment['integration_id'], str(payment['payment_id'])))
        done = cur.fetchone()
        if done:
            return 'skipped', {'payment': payment}, (
                f"По этому платежу сценарий уже создал документ (статус {done[0]}) - второй не нужен")
    is_refund = (scenario.get('template') or {}).get('operation') == 'sell_refund'
    if is_refund and payment['status'] in ('CANCELED', 'REFUNDED'):
        # Отмена/возврат: чек возврата нужен, только если по платежу был чек продажи.
        # Отмена удержания (двухстадийная оплата без списания) чека не требует.
        cur.execute(f'''
            SELECT EXISTS (
                SELECT 1 FROM {SCHEMA}.webhook_payments wp2
                WHERE wp2.integration_id = %s AND wp2.payment_id = %s AND (
                    wp2.receipt_id IS NOT NULL OR EXISTS (
                        SELECT 1 FROM {SCHEMA}.automation_documents d
                        WHERE d.payment_row_id = wp2.id AND d.operation = 'sell' AND d.status <> 'fail')))
        ''', (payment['integration_id'], str(payment['payment_id'])))
        if not cur.fetchone()[0]:
            return 'skipped', {'payment': payment}, 'По платежу не было чека продажи - чек возврата не нужен'
    if payment['receipt_id'] and scenario['action_template'] == 'regular' and not is_refund:
        return 'skipped', {'payment': payment}, 'По платежу уже есть чек в кассе'
    if (job.get('payload') or {}).get('reason') == 'discrepancy':
        # Расхождение: пока задание ждало, чек мог прийти - перепроверяем, чтобы не задвоить.
        has_receipt = payment['receipt_id'] is not None
        if not has_receipt:
            cur.execute(f'''
                SELECT EXISTS (SELECT 1 FROM {SCHEMA}.automation_documents d
                               WHERE d.payment_row_id = %s AND d.doc_kind = 'receipt' AND d.job_id <> %s)
            ''', (payment['id'], job['id']))
            has_receipt = bool(cur.fetchone()[0])
        if has_receipt:
            return 'skipped', {'payment': payment}, 'Чек по платежу уже есть или его пробивает другое задание - второй не нужен'
        mode = (scenario.get('field_mapping') or {}).get('verify_mode')
        if mode in ('payment_system', 'bank') and not job.get('verified'):
            if mode == 'bank':
                verdict, message, _ = payment_verify.verify_bank(
                    cur, job['company_id'], [payment['payment_id'], payment.get('order_id')], [payment['id']])
            else:
                verdict, message, _ = payment_verify.verify_payment(cur, job['company_id'], payment)
            where = 'Проверка в банке' if mode == 'bank' else 'Проверка в платёжной системе'
            if verdict == 'not_paid':
                return 'skipped', {'payment': payment}, f'{where}: {message} - чек не пробиваем'
            if verdict != 'paid':
                return 'error', {'payment': payment}, f'{where}: {message}'
            log(cur, job['id'], 'info', f'{where}: {message}')

    data: Dict[str, Any] = {
        'payment': payment,
        'customer': {'email': payment['customer_email'], 'phone': payment['customer_phone']},
        'items': None,
        'items_source': None
    }

    provider_name = CART_FROM_PROVIDER.get(payment['provider_slug'])
    if provider_name:
        cart = _cart(cur, payment['integration_id'], str(payment['payment_id']))
        if (not cart or not cart['items']) and payment['provider_slug'] in ('alfabank', 'tochka_acquiring', 'yookassa'):
            # У Альфа-Банка, Точки и ЮKassa состав заказа не приходит в уведомлении - дозапрашиваем.
            fetch = {'alfabank': _fetch_alfabank_cart, 'tochka_acquiring': _fetch_tochka_cart,
                     'yookassa': _fetch_yookassa_cart}[payment['provider_slug']]
            cart_error = fetch(cur, job['company_id'], payment)
            cart = _cart(cur, payment['integration_id'], str(payment['payment_id']))
            if not cart:
                return 'error', data, f'Не удалось получить корзину заказа у {provider_name}: {cart_error}'
        if not cart:
            return 'error', data, f'Ждём корзину от {provider_name} (уведомление с составом чека ещё не пришло)'
        if not cart['items']:
            if payment['provider_slug'] == 'tochka_acquiring':
                return 'error', data, ('В платёжной ссылке Точки нет товаров - для чека передавайте Items '
                                       'при создании ссылки (метод с чеком payments_with_receipt)')
            if payment['provider_slug'] == 'yookassa':
                return _yookassa_single_item(payment, data, scenario)
            if payment['provider_slug'] == 'cloudpayments':
                return _cloudpayments_single_item(payment, data, scenario)
            if payment['provider_slug'] == 'alfabank':
                if payment.get('payment_provider') == 'СБП' and not payment.get('order_id'):
                    return 'error', data, ('Оплата по статическому QR-коду СБП - у такого платежа нет корзины. '
                                           'Для чека нужен заказ с корзиной (динамический QR или платёжная страница)')
                return _alfabank_single_item(cur, payment, data, scenario)
            return 'error', data, f'{provider_name} прислал уведомление без товаров'
        receipt = cart['receipt']
        data['items'] = cart['items']
        data['items_source'] = provider_name
        data['taxation'] = receipt.get('Taxation')
        data['customer'] = {
            'email': receipt.get('Email') or payment['customer_email'],
            'phone': receipt.get('Phone') or payment['customer_phone'],
            'name': receipt.get('Customer'),
            'inn': receipt.get('CustomerInn')
        }
        data['provider_receipt'] = cart['fiscal']
        diff = round(cart['items_total'] - payment['amount'], 2)
        note = f', расхождение с платежом {diff:+.2f} ₽' if abs(diff) >= 0.01 else ''
        if cart['fiscalized']:
            data['existing_receipt_id'] = cart['receipt_id']
            if scenario['action_template'] == 'regular' and not is_refund:
                return 'skipped', data, (
                    f"Касса {provider_name} уже пробила чек (ФН {cart['fiscal'].get('FnNumber')}, "
                    f"ФД {cart['fiscal'].get('FiscalDocumentNumber')}) - второй обычный чек не нужен"
                )
            note += f", касса {provider_name} уже пробила чек (ФН {cart['fiscal'].get('FnNumber')})"
        else:
            note += f', касса {provider_name} чек не пробила - пробиваем сами'
        return 'ready', data, (
            f"Корзина от {provider_name}: {len(cart['items'])} поз. на {cart['items_total']:.2f} ₽ "
            f"(платёж #{payment['payment_id']}{note})"
        )

    if payment['provider_slug'] == 'moyklass':
        return prepare_moyklass(cur, payment, data, scenario)

    if payment['provider_slug'] == 'realtycalendar':
        return prepare_realtycalendar(payment, data, scenario)

    if payment['provider_slug'] == 'ecomkassa_gateway':
        # Платёж через шлюз Екомкассы (Точка и др.): идентификатор платежа = номер
        # документа в Екомкассе, корзину читаем оттуда же в формате АТОЛ Онлайн.
        kassa = company_cash_register(cur, job['company_id'])
        if not kassa:
            return 'error', data, 'Не найдена активная касса Екомкассы для чтения корзины'
        atol, err = get_receipt_atol(kassa, str(payment['payment_id']))
        if not atol:
            return 'error', data, err
        receipt = atol['receipt']
        items = receipt.get('items') or []
        if not items:
            return 'error', data, f"В документе Екомкассы #{payment['payment_id']} нет товаров"
        client = receipt.get('client') or {}
        data['items'] = items
        data['items_format'] = 'atol'
        data['payments'] = receipt.get('payments') or []
        data['items_source'] = 'Екомкасса'
        data['source_company'] = receipt.get('company') or {}
        data['taxation'] = (receipt.get('company') or {}).get('sno')
        data['customer'] = {
            'email': client.get('email') or payment['customer_email'],
            'phone': client.get('phone') or payment['customer_phone'],
            'name': client.get('name'), 'inn': client.get('inn')
        }
        total = round(sum(float(i.get('sum') or 0) for i in items), 2)
        diff = round(total - payment['amount'], 2)
        note = f', расхождение с платежом {diff:+.2f} ₽' if abs(diff) >= 0.01 else ''
        return 'ready', data, (
            f"Корзина из Екомкассы: {len(items)} поз. на {total:.2f} ₽ (платёж #{payment['payment_id']}{note})"
        )

    return 'ready', data, f"Собраны данные платежа #{payment['payment_id']} на {payment['amount']:.2f} ₽"


def _integration_config(cur, integration_id: int) -> Dict[str, Any]:
    cur.execute(f'SELECT config FROM {SCHEMA}.user_integrations WHERE id = %s', (integration_id,))
    row = cur.fetchone()
    config = row[0] if row else {}
    return json.loads(config) if isinstance(config, str) else (config or {})


def prepare_moyklass(cur, payment: Dict[str, Any], data: Dict[str, Any],
                     scenario: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''
    Платёж (CONFIRMED) или списание (OFFSET) «Мой Класс»: дозапрашиваем ученика, абонемент, вид абонемента,
    группу и программу, собираем чек по сопоставлению полей сценария (moyklass_crm) - название и сумма
    позиции шаблонами с подстановкой полей, контакты покупателя из выбранных полей.
    Признак расчёта ставит шаблон действия: оплата - предоплата (частичная, если абонемент оплачен
    не полностью), списание - полный расчёт с зачётом аванса.
    '''
    raw = payment.get('raw') or {}
    obj = raw.get('object') if isinstance(raw.get('object'), dict) else {}
    offset = payment['status'] == 'OFFSET'
    config = _integration_config(cur, payment['integration_id'])
    allowed = [str(v) for v in (config.get('payment_type_ids') or []) if str(v).strip()]
    type_id = obj.get('paymentTypeId')
    if not offset and allowed and str(type_id) not in allowed:
        return 'skipped', data, f'Способ оплаты #{type_id} не выбран в интеграции «Мой Класс» - чек не создаётся'

    record, err = moyklass_crm.load_record(str(config.get('api_key') or '').strip(), obj)
    if err:
        return 'error', data, err
    built, err, note = moyklass_crm.build_data(
        record, _template_vat_mapping(scenario.get('field_mapping') or {}, scenario, 'single'), offset)
    if err:
        return 'error', data, err
    data.update(built)
    item = built['items'][0] if built['items'] else {}
    customer = built['customer']
    contact = customer.get('phone') or customer.get('email') or 'нет контакта'
    total = sum(i['sum'] for i in built['items'])
    extra = f" и ещё {len(built['items']) - 1} поз." if len(built['items']) > 1 else ''
    return 'ready', data, (
        f"{'Списание (зачёт аванса)' if offset else 'Платёж'} «Мой Класс» #{payment['payment_id']}: "
        f"«{item.get('name', '')}»{extra} "
        f"на {total:.2f} ₽, ученик {customer.get('name') or obj.get('userId')} ({contact}){note}"
    )


def prepare_realtycalendar(payment: Dict[str, Any], data: Dict[str, Any],
                           scenario: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''
    Платёж/возврат RealtyCalendar: всё уже есть в вебхуке (бронь, гость, объект, платёж) -
    собираем чек по сопоставлению полей сценария (realtycalendar_crm), без запросов в API РК.
    '''
    raw = payment.get('raw') or {}
    record = realtycalendar_crm.record_from_raw(raw)
    refund = payment['status'] == 'REFUNDED'
    built, err, note = realtycalendar_crm.build_data(
        record, _template_vat_mapping(scenario.get('field_mapping') or {}, scenario, 'single'), refund)
    if err:
        return 'error', data, err
    data.update(built)
    item = built['items'][0] if built['items'] else {}
    customer = built['customer']
    total = sum(i['sum'] for i in built['items'])
    extra = f" и ещё {len(built['items']) - 1} поз." if len(built['items']) > 1 else ''
    contact = customer.get('phone') or customer.get('email') or 'нет контакта'
    booking = record.get('booking') or {}
    return 'ready', data, (
        f"{'Возврат' if refund else 'Платёж'} RealtyCalendar #{payment['payment_id']} по брони #{booking.get('id')}: "
        f"«{item.get('name', '')}»{extra} на {total:.2f} ₽, гость {customer.get('name') or '—'} ({contact}){note}"
    )


def _crm_source(cur, scenario_id: int) -> Tuple[str, Dict[str, Any]]:
    '''Провайдер (bitrix24 / amocrm) и настройки интеграции-источника сценария.'''
    cur.execute(f'''
        SELECT p.slug, ui.config FROM {SCHEMA}.automation_scenarios s
        JOIN {SCHEMA}.user_integrations ui ON ui.id = s.source_integration_id
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE s.id = %s
    ''', (scenario_id,))
    row = cur.fetchone()
    if not row:
        return '', {}
    config = json.loads(row[1]) if isinstance(row[1], str) else (row[1] or {})
    return row[0], config


def prepare_crm(cur, job: Dict[str, Any], scenario: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''
    Сделка/лид Битрикс24 или сделка AmoCRM: свежие данные из CRM (сделка + контакт + компания + товары),
    проверка стадии запуска, сбор позиций и покупателя по сопоставлению полей сценария.
    '''
    entity = 'lead' if job['source_type'] == 'crm_lead' else 'deal'
    noun = 'Сделка' if entity == 'deal' else 'Лид'
    mapping = _template_vat_mapping({**bitrix_crm.DEFAULT_MAPPING, **(scenario.get('field_mapping') or {})}, scenario, 'products')
    slug, config = _crm_source(cur, scenario['id'])
    if slug == 'amocrm':
        entity = 'deal'
        record, err = amocrm_crm.load_record(config, job['source_id'])
    else:
        record, err = bitrix_crm.load_record(config.get('webhook_url', ''), entity, job['source_id'])
    if err:
        return 'error', {}, err
    main = record[entity]
    if not bitrix_crm.stage_matches(mapping, entity, main):
        return 'skipped', {'crm': {'entity': entity, 'id': job['source_id']}}, (
            f"{noun} #{job['source_id']} в воронке {main.get('CATEGORY_ID', '-')}, а сценарий настроен на воронку "
            f"{mapping.get('pipeline')} - документ не создаётся"
        )
    ok, actual = bitrix_crm.condition_check(mapping, entity, record)
    if not ok:
        field = mapping.get('condition_field_title') or mapping.get('condition_field')
        wanted = mapping.get('condition_values_text') or ', '.join(mapping.get('condition_values') or []) or 'любое заполненное'
        return 'skipped', {'crm': {'entity': entity, 'id': job['source_id']}}, (
            f"{noun} #{job['source_id']}: поле «{field}» "
            f"{'не заполнено' if not actual else f'= «{actual}»'}, а сценарий запускается при «{wanted}» - документ не создаётся"
        )
    data, err, note = (amocrm_crm.build_data(record, mapping) if slug == 'amocrm'
                       else bitrix_crm.build_data(record, entity, mapping))
    if err:
        return 'error', {}, err
    total = sum(i['sum'] for i in data['items'])
    return 'ready', data, (
        f"{noun} #{job['source_id']} «{main.get('TITLE') or ''}»: {len(data['items'])} поз. на {total:.2f} ₽{note}"
    )


def retry_delay(attempts: int) -> Optional[int]:
    return RETRY_DELAYS[attempts - 1] if attempts - 1 < len(RETRY_DELAYS) else None


def log(cur, job_id: int, level: str, message: str, details: Optional[Dict[str, Any]] = None):
    cur.execute(
        f'INSERT INTO {SCHEMA}.automation_job_log (job_id, level, message, details) VALUES (%s, %s, %s, %s)',
        (job_id, level, message, json.dumps(details, ensure_ascii=False, default=str) if details else None)
    )

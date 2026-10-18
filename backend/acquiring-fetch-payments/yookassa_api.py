'''
ЮKassa (API v3, https://yookassa.ru/developers/using-api/webhooks).
Одинаковая копия лежит в webhook-receive и automation-jobs.

Уведомление: POST JSON {"type": "notification", "event": "payment.succeeded", "object": {...}}.
Подписи у уведомления нет - подлинность подтверждаем запросом объекта в API ЮKassa
по shopId + секретному ключу магазина (HTTP Basic): берём статус и сумму из ответа API.
Почты покупателя в платеже нет - её подставляет шаблон действия сценария (почта по умолчанию).
Состав чека: если магазин отправляет чеки через ЮKassa - позиции из GET /v3/receipts?payment_id=,
иначе одна позиция на сумму платежа с описанием платежа.
'''
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = 't_p83864310_fintech_payment_reco'
API_BASE = 'https://api.yookassa.ru/v3'

EVENT_STATUS = {
    'payment.waiting_for_capture': 'AUTHORIZED',
    'payment.succeeded': 'CONFIRMED',
    'payment.canceled': 'CANCELED',
    'refund.succeeded': 'REFUNDED',
}

NOTIFY_KEYS = {
    'AUTHORIZED': 'notify_on_authorized',
    'CONFIRMED': 'notify_on_confirmed',
    'REJECTED': 'notify_on_rejected',
    'CANCELED': 'notify_on_canceled',
    'REFUNDED': 'notify_on_refunded',
}

# Статус объекта в API, который подтверждает событие уведомления.
EXPECTED_API_STATUS = {
    'payment.waiting_for_capture': 'waiting_for_capture',
    'payment.succeeded': 'succeeded',
    'payment.canceled': 'canceled',
    'refund.succeeded': 'succeeded',
}

# Отмена магазином (в т.ч. не подтвердили удержание) - CANCELED, остальное - отказ в оплате.
MERCHANT_CANCEL_REASONS = ('canceled_by_merchant', 'expired_on_capture')

# vat_code ЮKassa -> ставка НДС кассы (АТОЛ).
VAT_CODES = {
    1: 'none', 2: 'vat0', 3: 'vat10', 4: 'vat20', 5: 'vat110', 6: 'vat120',
    7: 'vat5', 8: 'vat7', 9: 'vat105', 10: 'vat107', 11: 'vat22', 12: 'vat122',
}

PAYMENT_METHOD_NAMES = {
    'bank_card': 'Карта', 'sbp': 'СБП', 'yoo_money': 'ЮMoney', 'sberbank': 'SberPay',
    'tinkoff_bank': 'T-Pay', 'mir_pay': 'Mir Pay', 'sber_loan': 'Покупки в кредит',
    'sber_bnpl': 'Плати частями', 'alfabank': 'Альфа-Клик', 'b2b_sberbank': 'СберБизнес',
    'mobile_balance': 'Баланс телефона', 'cash': 'Наличные', 'electronic_certificate': 'Электронный сертификат',
}


def _auth_header(config: Dict[str, Any]) -> str:
    creds = f"{str(config.get('shop_id') or '').strip()}:{str(config.get('secret_key') or '').strip()}"
    return 'Basic ' + base64.b64encode(creds.encode('utf-8')).decode('ascii')


def api_get(config: Dict[str, Any], path: str, timeout: float = 8) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    '''GET к API ЮKassa от имени магазина. Returns: (данные, ошибка, HTTP-код; 0 - нет связи).'''
    req = urllib.request.Request(f'{API_BASE}{path}', headers={'Authorization': _auth_header(config)})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8')), None, resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace') if e.fp else ''
        try:
            desc = json.loads(body).get('description')
        except Exception:
            desc = None
        if e.code == 401:
            return None, 'ЮKassa: неверный shopId или секретный ключ', 401
        return None, f'ЮKassa ответила ошибкой {e.code}' + (f': {desc}' if desc else ''), e.code
    except Exception as e:
        return None, f'Не удалось связаться с ЮKassa: {str(e)[:120]}', 0


def is_retryable(error: Optional[str]) -> bool:
    '''Сбой связи или 5xx ЮKassa - уведомление стоит принять повторно.'''
    e = error or ''
    return e.startswith('Не удалось связаться с ЮKassa') or e.startswith('ЮKassa ответила ошибкой 5')


def _amount(obj: Dict[str, Any]) -> float:
    try:
        return round(float((obj.get('amount') or {}).get('value') or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def payment_method_name(payment: Dict[str, Any]) -> Optional[str]:
    method = (payment or {}).get('payment_method') or {}
    kind = method.get('type')
    return PAYMENT_METHOD_NAMES.get(kind, kind) if kind else None


def convert_items(receipt: Dict[str, Any]) -> List[Dict[str, Any]]:
    '''Позиции чека ЮKassa -> наш формат корзины (суммы в рублях).'''
    items = []
    for it in receipt.get('items') or []:
        if not isinstance(it, dict):
            continue
        quantity = float(it.get('quantity') or 0)
        price = round(float((it.get('amount') or {}).get('value') or 0), 2)
        try:
            vat = VAT_CODES.get(int(it.get('vat_code')))
        except (TypeError, ValueError):
            vat = None
        items.append({
            'name': str(it.get('description') or 'Товар')[:128],
            'price': price,
            'quantity': quantity,
            'amount': round(price * quantity, 2),
            'tax': vat,
            'payment_method': it.get('payment_mode'),
            'payment_object': it.get('payment_subject'),
            'measurement_unit': it.get('measure') if it.get('measure') and it.get('measure') != 'piece' else None,
            'country_code': it.get('country_of_origin_code'),
            'declaration_number': it.get('customs_declaration_number'),
            'excise': (it.get('excise') or None),
            'mark_code': ((it.get('mark_code_info') or {}).get('gs_1m') if isinstance(it.get('mark_code_info'), dict) else None),
        })
    return items


def save_cart(cur, integration_id: int, company_id: int, payment: Dict[str, Any],
              receipts: List[Dict[str, Any]]) -> int:
    '''
    Корзина платежа: из чека прихода ЮKassa (если магазин отправляет чеки через ЮKassa).
    Чека нет - пустая корзина: сценарий пробьёт чек одной позицией на сумму платежа.
    '''
    sale = next((r for r in receipts if r.get('type') == 'payment' and r.get('status') != 'canceled'), None)
    items = convert_items(sale) if sale else []
    fiscalized = bool(sale and sale.get('status') == 'succeeded' and sale.get('fiscal_document_number'))
    fiscal = {}
    if sale:
        fiscal = {
            'FnNumber': sale.get('fiscal_storage_number'),
            'FiscalDocumentNumber': sale.get('fiscal_document_number'),
            'FiscalDocumentAttribute': sale.get('fiscal_attribute'),
            'ReceiptDatetime': sale.get('registered_at'),
            'Status': sale.get('status'),
            'YookassaReceiptId': sale.get('id'),
        }
        fiscal = {k: v for k, v in fiscal.items() if v is not None}
    customer = (sale or {}).get('customer') or {}
    receipt = {
        'Email': customer.get('email'), 'Phone': customer.get('phone'),
        'Customer': customer.get('full_name'), 'CustomerInn': customer.get('inn'),
        'Taxation': None, 'description': payment.get('description'),
    }
    total = round(sum(i['amount'] for i in items), 2)
    cur.execute(f'''
        INSERT INTO {SCHEMA}.payment_carts
            (company_id, integration_id, payment_id, order_id, source, items, receipt, items_total, fiscal_data,
             fiscalized, receipt_id)
        VALUES (%s, %s, %s, %s, 'yookassa_receipt', %s, %s, %s, %s, %s, NULL)
        ON CONFLICT (integration_id, payment_id) DO UPDATE SET
            items = EXCLUDED.items, receipt = EXCLUDED.receipt, items_total = EXCLUDED.items_total,
            fiscal_data = EXCLUDED.fiscal_data,
            fiscalized = payment_carts.fiscalized OR EXCLUDED.fiscalized,
            order_id = COALESCE(EXCLUDED.order_id, payment_carts.order_id), updated_at = NOW()
    ''', (company_id, integration_id, str(payment.get('id')), _order_id(payment),
          json.dumps(items, ensure_ascii=False), json.dumps(receipt, ensure_ascii=False), total,
          json.dumps(fiscal, ensure_ascii=False), fiscalized))
    return len(items)


def fetch_receipts(config: Dict[str, Any], payment_id: str, timeout: float = 8) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    data, err, code = api_get(config, f'/receipts?payment_id={urllib.parse.quote(payment_id)}', timeout)
    if data is None:
        # Магазину без чеков ЮKassa список чеков может быть недоступен - это не ошибка.
        if code in (403, 404):
            return [], None
        return None, err
    return [r for r in data.get('items') or [] if isinstance(r, dict)], None


def _order_id(payment: Dict[str, Any]) -> Optional[str]:
    meta = payment.get('metadata') or {}
    for key in ('order_id', 'orderId', 'orderNumber', 'order_number', 'cms_name_order_id'):
        if meta.get(key):
            return str(meta[key])[:100]
    return None


def process(cur, integration_id: int, company_id: int, config: Dict[str, Any],
            webhook_settings: Dict[str, Any], body: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[str], Optional[str]]:
    '''
    Уведомление ЮKassa: событие -> запрос объекта в API (подлинность и актуальный статус) -> платёж.
    Returns: (подлинное, webhook_payment_id, ошибка, пометка «пропущено»)
    '''
    event = str(body.get('event') or '')
    obj = body.get('object') if isinstance(body.get('object'), dict) else {}
    obj_id = str(obj.get('id') or '').strip()
    if body.get('type') != 'notification' or not obj_id:
        return True, None, 'Это не уведомление ЮKassa (нет event / object.id)', None
    status = EVENT_STATUS.get(event)
    if not status:
        return True, None, None, f'Событие {event} не обрабатываем'

    is_refund = event.startswith('refund.')
    api_obj, err, code = api_get(config, f"/{'refunds' if is_refund else 'payments'}/{urllib.parse.quote(obj_id)}")
    if api_obj is None:
        if code == 404:
            return False, None, f'ЮKassa не знает {"возврат" if is_refund else "платёж"} {obj_id} в этом магазине - уведомление отклонено', None
        return True, None, err, None
    if api_obj.get('status') != EXPECTED_API_STATUS[event]:
        return True, None, (f"Статус в ЮKassa «{api_obj.get('status')}» не совпадает с уведомлением {event} "
                            f"- уведомление не принято"), None

    if is_refund:
        payment_id = str(api_obj.get('payment_id') or '')
        payment, err, _ = api_get(config, f'/payments/{urllib.parse.quote(payment_id)}')
        payment = payment or {'id': payment_id}
        amount = _amount(api_obj)
    else:
        payment = api_obj
        payment_id = obj_id
        amount = _amount(payment)
        if status == 'CANCELED':
            reason = (payment.get('cancellation_details') or {}).get('reason')
            status = 'CANCELED' if reason in MERCHANT_CANCEL_REASONS else 'REJECTED'

    notify_key = NOTIFY_KEYS.get(status)
    if notify_key and not webhook_settings.get(notify_key, True):
        return True, None, None, 'Статус выключен в настройках уведомлений интеграции'

    method = payment.get('payment_method') or {}
    card = method.get('card') or {}
    pan = f"{card.get('first6', '')}******{card.get('last4')}" if card.get('last4') else None
    reason = (payment.get('cancellation_details') or {}).get('reason')
    raw = {'notification': body, 'payment': payment, 'refund': api_obj if is_refund else None}
    cur.execute(f'''
        INSERT INTO {SCHEMA}.webhook_payments (
            integration_id, company_id, payment_id, terminal_key, amount, order_id, status, payment_status,
            error_code, customer_email, customer_phone, pan, card_type, exp_date, raw_data, payment_provider, origin
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s, %s, %s, %s, 'webhook')
        ON CONFLICT (integration_id, payment_id, status) DO NOTHING
        RETURNING id
    ''', (
        integration_id, company_id, payment_id, str(config.get('shop_id') or '')[:50] or None, amount,
        _order_id(payment), status, api_obj.get('status'),
        (str(reason)[:10] if status in ('REJECTED', 'CANCELED') and reason else None),
        pan, (str(card.get('card_type'))[:20] if card.get('card_type') else None),
        f"{card.get('expiry_month')}/{str(card.get('expiry_year') or '')[-2:]}" if card.get('expiry_month') else None,
        json.dumps(raw, ensure_ascii=False), payment_method_name(payment),
    ))
    row = cur.fetchone()
    return True, (row[0] if row else None), None, None

import re
from datetime import date, datetime, timedelta, timezone
import json
from typing import Any, Dict, List, Optional, Tuple

from ecomkassa_client import cash_register, create_courier_order, create_fiscal_receipt, deliver_courier_order, order_status, store_address
from receipt_dictionaries import MEASURES, PAYMENT_OBJECTS_V5

SCHEMA = 't_p83864310_fintech_payment_reco'
MSK = timezone(timedelta(hours=3))


def _atol_items(data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    '''Позиции в формате АТОЛ. Корзина Т-Банка переводится, корзина Екомкассы уже в нужном формате.'''
    items = data.get('items') or []
    if data.get('items_format') == 'atol':
        return items
    result = []
    for i in items:
        item = {
            'name': i.get('name'), 'price': i.get('price'), 'quantity': i.get('quantity'),
            'sum': i.get('amount'), 'measurement_unit': i.get('measurement_unit') or 'шт',
            'payment_method': i.get('payment_method') or 'full_payment',
            'payment_object': i.get('payment_object') or 'commodity',
            'vat': {'type': i.get('tax') or 'none'}
        }
        if isinstance(i.get('agent_data'), dict):
            item['agent_info'] = {'type': i['agent_data'].get('AgentSign')}
        if isinstance(i.get('supplier_info'), dict):
            item['supplier_info'] = {k.lower(): v for k, v in i['supplier_info'].items()}
        result.append(item)
    return result


def apply_template(items: List[Dict[str, Any]], template: Dict[str, Any]) -> List[Dict[str, Any]]:
    '''
    Проставляет в позиции признак расчёта, предмет расчёта и единицу измерения из шаблона.
    v4: payment_object строкой, measurement_unit строкой; v5: payment_object и measure числами.
    '''
    v5 = template.get('protocol_version') == 'v5'
    result = []
    for i in items:
        item = dict(i)
        if template.get('payment_method'):
            item['payment_method'] = template['payment_method']
        obj = template.get('payment_object')
        if obj:
            item['payment_object'] = PAYMENT_OBJECTS_V5[obj] if v5 else ('commodity' if obj == 'commodity_marked' else obj)
        measure = MEASURES.get(template.get('measure') or '')
        if measure:
            if v5:
                item.pop('measurement_unit', None)
                item['measure'] = measure['v5']
            else:
                item.pop('measure', None)
                item['measurement_unit'] = measure['v4']
        result.append(item)
    return result


def document_operation(template: Dict[str, Any]) -> str:
    '''Операция в URL: sell / sell_refund, для чека коррекции - *_correction.'''
    operation = template.get('operation') or 'sell'
    if template.get('receipt_type') == 'correction':
        return f'{operation}_correction'
    return operation


def correction_info(template: Dict[str, Any], data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    '''
    correction_info чека коррекции (только самостоятельная, type = self), по АТОЛ Онлайн:
    v4 (ФФД 1.05) - base_date, base_number, base_name - все обязательны (теги 1178, 1179, 1177);
    v5 (ФФД 1.2) - base_date (дата корректируемого расчёта), base_number - если указан.
    '''
    if template.get('receipt_type') != 'correction':
        return None, ''
    if template.get('correction_date_source') == 'today':
        base_date = datetime.now(timezone(timedelta(hours=3))).date()
    elif template.get('correction_date_source') == 'client' and not template.get('correction_base_date'):
        return None, 'Не указана дата документа-основания коррекции - заполните в сценарии'
    elif template.get('correction_date_source') in ('fixed', 'client') and template.get('correction_base_date'):
        base = template['correction_base_date']
        base_date = base if isinstance(base, date) else datetime.strptime(str(base)[:10], '%Y-%m-%d').date()
    else:
        paid_at = (data.get('payment') or {}).get('created_at')
        if not paid_at:
            return None, 'Нет даты платежа для основания коррекции'
        base_date = datetime.fromisoformat(paid_at).date()
    info = {'type': 'self', 'base_date': base_date.strftime('%d.%m.%Y')}
    number = str(template.get('correction_base_number') or '').strip()
    if template.get('protocol_version') == 'v5':
        if number:
            info['base_number'] = number
        return info, ''
    name = str(template.get('correction_base_name') or '').strip()
    if not number:
        return None, 'Не указан номер документа-основания коррекции (обязателен для v4) - заполните в шаблоне или сценарии'
    if not name:
        return None, 'Не указано описание коррекции (обязательно для v4) - заполните в шаблоне или сценарии'
    info['base_number'] = number
    info['base_name'] = name
    return info, ''


def agent_blocks(template: Dict[str, Any], crm: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    '''
    Агентский чек по АТОЛ Онлайн: agent_info (признак агента + платёжный агент,
    оператор по приёму платежей, оператор перевода) и supplier_info (поставщик).
    Поставщик: заданное в шаблоне > поле из CRM (сделка) > введённое в сценарии.
    Returns: (agent_info, supplier_info) - пустые блоки и поля не передаём.
    '''
    a = template.get('agent_settings')
    if template.get('receipt_type') != 'agent' or not isinstance(a, dict) or not a.get('agent_type'):
        return None, None
    a = dict(a)
    base = template.get('agent_template') or {}
    for key, value in (crm or {}).items():
        if value and base.get(key) in (None, '', []):
            a[key] = value
    clean = lambda d: {k: v for k, v in d.items() if v}
    agent = {'type': a['agent_type']}
    paying = clean({'operation': a.get('paying_agent_operation'), 'phones': a.get('paying_agent_phones')})
    if paying:
        agent['paying_agent'] = paying
    receive = clean({'phones': a.get('receive_payments_operator_phones')})
    if receive:
        agent['receive_payments_operator'] = receive
    transfer = clean({'phones': a.get('money_transfer_operator_phones'), 'name': a.get('money_transfer_operator_name'),
                      'address': a.get('money_transfer_operator_address'), 'inn': a.get('money_transfer_operator_inn')})
    if transfer:
        agent['money_transfer_operator'] = transfer
    supplier = clean({'phones': a.get('supplier_phones'), 'name': a.get('supplier_name'), 'inn': a.get('supplier_inn')})
    return agent, supplier or None


def apply_agent(receipt: Dict[str, Any], template: Dict[str, Any], crm: Optional[Dict[str, Any]] = None) -> None:
    '''
    Раскладывает агентские данные по версии протокола:
    v4 (ФФД 1.05) - agent_info и телефоны поставщика общие на весь чек (receipt.agent_info,
        receipt.supplier_info), наименование и ИНН поставщика - в supplier_info каждой позиции;
    v5 (ФФД 1.2) - agent_info и supplier_info (телефоны, наименование, ИНН) в каждой позиции.
    '''
    agent, supplier = agent_blocks(template, crm)
    if not agent:
        return
    supplier = supplier or {}
    if template.get('protocol_version') == 'v5':
        for item in receipt['items']:
            item['agent_info'] = agent
            if supplier:
                item['supplier_info'] = supplier
        return
    receipt['agent_info'] = agent
    if supplier.get('phones'):
        receipt['supplier_info'] = {'phones': supplier['phones']}
    item_supplier = {k: v for k, v in supplier.items() if k in ('name', 'inn')}
    for item in receipt['items']:
        item.pop('agent_info', None)
        if item_supplier:
            item['supplier_info'] = item_supplier
        else:
            item.pop('supplier_info', None)


WEBHOOK_RECEIVE_URL = 'https://functions.poehali.dev/a923b457-57a6-4eb2-b566-9a9d65cb04e8'


def callback_url(cur, company_id: Optional[int]) -> Optional[str]:
    '''
    Адрес, куда Екомкасса пришлёт уведомление о пробитом чеке по заказу (формат АТОЛ:
    status done/fail, uuid, payload с реквизитами). Принимает интеграция «Екомкасса — платёжный шлюз»,
    а если её нет - сама интеграция кассы: чек в любом случае сохраняется к кассе компании.
    '''
    if cur is None or not company_id:
        return None
    cur.execute(f'''
        SELECT ui.webhook_token FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug IN ('ecomkassa_gateway', 'ecomkassa') AND ui.status = 'active'
          AND ui.webhook_token IS NOT NULL
        ORDER BY (p.slug = 'ecomkassa_gateway') DESC, ui.id LIMIT 1
    ''', (company_id,))
    row = cur.fetchone()
    return f'{WEBHOOK_RECEIVE_URL}?token={row[0]}' if row else None


def save_pending_order(cur, integration_id: int, company_id: Optional[int], order_id: str,
                       raw: Dict[str, Any], total: float) -> None:
    '''
    Заказ создан в Екомкассе - сразу сохраняем его со статусом wait ("В работе"),
    не дожидаясь колбэка: так он появляется в реестре в группе с платежом.
    Пробитый заказ (done) не трогаем. Логика та же, что в webhook-receive.
    '''
    if cur is None or not company_id:
        return
    raw = {k: v for k, v in raw.items() if v is not None}
    raw['status'] = 'wait'
    cur.execute(f'''
        INSERT INTO {SCHEMA}.ecomkassa_receipts (
            integration_id, company_id, order_id, legacy_no, status, total_sum, raw_data, order_type, origin
        ) VALUES (%s, %s, %s, %s, 'wait', %s, %s, 'CORD', 'automation')
        ON CONFLICT (integration_id, order_id) DO UPDATE SET
            total_sum = COALESCE(EXCLUDED.total_sum, {SCHEMA}.ecomkassa_receipts.total_sum),
            raw_data = {SCHEMA}.ecomkassa_receipts.raw_data || EXCLUDED.raw_data
        WHERE {SCHEMA}.ecomkassa_receipts.status = 'wait'
    ''', (integration_id, company_id, order_id, order_id, total, json.dumps(raw, ensure_ascii=False)))


def register_document(cur, job: Dict[str, Any], scenario: Dict[str, Any], kassa_id: int, external_id: str,
                      operation: str, total: float, advance: float, ecom_uuid: Optional[str] = None,
                      doc_kind: str = 'order') -> None:
    '''
    Реестр документов автоматизации: каждый документ, отправленный нами в кассу,
    связан с платежом-основанием через external_id (наш номер) и UUID кассы.
    По ним колбэк кассы довязывает пробитый чек, реестр транзакций собирает
    цепочку, а сверка знает, какая часть суммы - зачёт аванса.
    operation: sell / sell_refund (+ _correction); doc_kind: order (заказ) / receipt (чек).
    '''
    if cur is None or not job.get('company_id'):
        return
    payment_row_id = int(job['source_id']) if job.get('source_type') == 'payment' and str(job.get('source_id') or '').isdigit() else None
    cur.execute(f'''
        INSERT INTO {SCHEMA}.automation_documents
            (company_id, job_id, scenario_id, payment_row_id, kassa_integration_id, doc_kind, operation,
             external_id, ecom_uuid, total_sum, advance_sum)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (kassa_integration_id, external_id) DO UPDATE SET
            ecom_uuid = COALESCE(EXCLUDED.ecom_uuid, {SCHEMA}.automation_documents.ecom_uuid),
            total_sum = EXCLUDED.total_sum, advance_sum = EXCLUDED.advance_sum,
            operation = EXCLUDED.operation, updated_at = NOW()
    ''', (job['company_id'], job.get('id'), scenario.get('id'), payment_row_id, kassa_id, doc_kind, operation,
          external_id, ecom_uuid, total, advance))
    if ecom_uuid:
        # Колбэк кассы мог прийти раньше - сразу довязываем уже сохранённый чек.
        cur.execute(f'''
            UPDATE {SCHEMA}.automation_documents d
            SET receipt_id = ekr.id, status = ekr.status, updated_at = NOW()
            FROM {SCHEMA}.ecomkassa_receipts ekr
            WHERE d.kassa_integration_id = %s AND d.external_id = %s
              AND ekr.integration_id = d.kassa_integration_id AND ekr.order_id = d.ecom_uuid
              AND ekr.removed_at IS NULL
        ''', (kassa_id, external_id))


def make_external_id(job: Dict[str, Any], data: Dict[str, Any], seller_inn: Optional[str], operation: str) -> str:
    '''
    Номер заказа (external_id) для кассы - по нему потом сверяем чек с платежом и сделкой:
    - есть и сделка/лид CRM, и платёж из банка: номер сделки-номер платежа (46480-115014397);
    - только сделка/лид: ИНН-номер сделки (номера сделок у разных клиентов совпадают, ИНН делает их уникальными);
    - только платёж: ИНН-номер платежа.
    Лид - с буквой L (L7). Возврат/коррекция - с суффиксом операции, чтобы не совпасть с чеком прихода.
    Не из чего собрать - auto-<id задания>, как раньше.
    '''
    inn = re.sub(r'\D', '', seller_inn or '')
    crm = data.get('crm') or {}
    payment_ref = str((data.get('payment') or {}).get('payment_id') or '').strip()
    mk_ref = re.sub(r'[^\w-]', '', str((data.get('moyklass') or {}).get('order_id') or ''))
    if mk_ref:
        # «Мой Класс»: номер из сопоставления полей сценария (по умолчанию - ID платежа).
        payment_ref = mk_ref
    if payment_ref and data.get('offset'):
        # Зачёт аванса «Мой Класс»: номер списания может совпасть с номером оплаты - отличаем.
        payment_ref = f'D{payment_ref}'
    crm_ref = f"{'L' if crm.get('entity') == 'lead' else ''}{crm['id']}" if crm.get('id') else ''
    if crm_ref and payment_ref:
        base = f'{crm_ref}-{payment_ref}'
    elif (crm_ref or payment_ref) and inn:
        base = f'{inn}-{crm_ref or payment_ref}'
    else:
        return f"auto-{job['id']}"
    suffix = '' if operation == 'sell' else f"-{operation.replace('sell_', '')}"
    return f'{base}{suffix}'[:128]


def create_order(cur, job: Dict[str, Any], scenario: Dict[str, Any], data: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''
    Создаёт заказ в Екомкассе (POST /api/mobile/v1/courier/:storeId/create/:operation).
    Параметры берутся из шаблона действия: операция и тип чека, признак/предмет расчёта,
    единица измерения, тип оплаты (пусто - без оплат), почта по умолчанию.
    Номер внешнего заказа - make_external_id (ИНН-платёж / ИНН-сделка): повтор дубля не создаст.
    Returns: (статус, результат, сообщение в журнал): done / error.
    '''
    kassa = cash_register(cur, scenario['target_integration_id'])
    if not kassa:
        return 'error', {}, 'Касса сценария не найдена, отключена или без номера магазина'
    if not kassa['token']:
        return 'error', {}, 'Нет токена Екомкассы и не удалось получить новый - переподключите кассу (логин и пароль)'
    items = _atol_items(data)
    if not items:
        return 'error', {}, 'В собранных данных нет товаров'

    template = scenario.get('template') or {}
    items = apply_template(items, template)
    total = round(sum(float(i.get('sum') or 0) for i in items), 2)
    source_company = dict(data.get('source_company') or {})
    if not source_company.get('inn') and cur is not None and job.get('company_id'):
        # Корзина не из Екомкассы (Т-Банк и др.) - реквизиты организации из карточки компании.
        cur.execute(f'SELECT inn FROM {SCHEMA}.companies WHERE id = %s', (job['company_id'],))
        row = cur.fetchone()
        if row and row[0]:
            source_company['inn'] = row[0]
    customer = data.get('customer') or {}
    client = {k: v for k, v in {'email': customer.get('email') or template.get('default_email'),
                                'phone': customer.get('phone'),
                                'name': customer.get('name'), 'inn': customer.get('inn')}.items() if v}
    company = {k: v for k, v in {'inn': source_company.get('inn'), 'sno': data.get('taxation') or source_company.get('sno'),
                                 'payment_address': source_company.get('payment_address'),
                                 'email': source_company.get('email')}.items() if v}
    payment_type = template.get('payment_type')
    paid = payment_type is not None
    operation = document_operation(template)
    correction, err = correction_info(template, data)
    if err:
        return 'error', {}, err
    external_id = make_external_id(job, data, source_company.get('inn'), operation)
    body = {
        'external_id': external_id,
        'timestamp': datetime.now(MSK).strftime('%d.%m.%Y %H:%M:%S'),
        'receipt': {
            'client': client,
            'company': company,
            'items': items,
            'payments': [{'type': int(payment_type), 'sum': total}] if paid else [],
            'total': total
        }
    }
    if correction:
        body['receipt']['correction_info'] = correction
    apply_agent(body['receipt'], template, data.get('agent'))
    notify_url = callback_url(cur, job.get('company_id'))
    if notify_url:
        body['service'] = {'callback_url': notify_url}
    advance = round(sum(float(p['sum']) for p in body['receipt']['payments'] if int(p['type']) == 2), 2)
    register_document(cur, job, scenario, kassa['id'], external_id, operation, total, advance)
    result, err = create_courier_order(kassa, operation, body)
    if not result:
        return 'error', {'request': body}, err
    order_id = str(result.get('uuid'))
    register_document(cur, job, scenario, kassa['id'], external_id, operation, total, advance, order_id)
    save_pending_order(cur, kassa['id'], job.get('company_id'), order_id, {
        'uuid': order_id, 'external_id': external_id, 'kind': 'COURIER_ORDER',
        'permalink': result.get('permalink'), 'timestamp': result.get('timestamp'),
    }, total)
    message = (
        f"Заказ создан в Екомкассе: #{order_id} на {total:.2f} ₽, "
        f"шаблон «{template.get('name')}», {'оплаченный' if paid else 'неоплаченный'} ({result.get('permalink', '')})"
    )
    outcome = {'request': body, 'response': result, 'external_id': external_id}
    if not template.get('auto_deliver'):
        return 'done', outcome, message

    # Повтор задания вернёт тот же заказ (external_id) - если доставка уже
    # подтверждена, второй раз не подтверждаем.
    if order_status(kassa, order_id) == 'PAID':
        return 'done', outcome, f'{message}. Доставка уже подтверждена'
    deliver_body = {k: v for k, v in {
        'cashierName': template.get('cashier_name'),
        'customerEmail': client.get('email'),
        'customerPhone': client.get('phone'),
    }.items() if v}
    # Предоплаченный заказ - пустой список оплат (касса зачтёт аванс сама).
    deliver_body['payments'] = []
    delivered, err = deliver_courier_order(kassa, order_id, deliver_body)
    outcome['deliver_request'] = deliver_body
    if delivered is None:
        return 'error', outcome, f'{message}. {err}'
    outcome['deliver_response'] = delivered
    return 'done', outcome, (
        f"{message}. Доставка подтверждена, заказ {delivered.get('status', 'PAID')} - "
        f"касса пробьёт чек и пришлёт уведомление"
    )


def create_receipt(cur, job: Dict[str, Any], scenario: Dict[str, Any], data: Dict[str, Any]) -> Tuple[str, Dict[str, Any], str]:
    '''
    Чек напрямую в Екомкассе (без заказа): обычный, агентский или коррекции - по шаблону действия.
    Состав - из собранной корзины (Т-Банк, Альфа, Екомкасса, CRM). Нет корзины - чек не пробиваем.
    Номер внешнего документа - make_external_id: повтор задания второй чек не пробьёт.
    Returns: (статус, результат, сообщение в журнал): done / error.
    '''
    kassa = cash_register(cur, scenario['target_integration_id'])
    if not kassa:
        return 'error', {}, 'Касса сценария не найдена, отключена или без номера магазина'
    if not kassa['token']:
        return 'error', {}, 'Нет токена Екомкассы и не удалось получить новый - переподключите кассу (логин и пароль)'
    template = scenario.get('template') or {}
    kassa['protocol_version'] = template.get('protocol_version') or kassa.get('protocol_version') or 'v4'
    items = _atol_items(data)
    if not items:
        return 'error', {}, 'Нет корзины товаров - чек не пробит. Проверьте платёж и пробейте чек вручную'
    items = apply_template(items, template)
    if data.get('offset') and int(template.get('payment_type') if template.get('payment_type') is not None else 1) != 2:
        return 'error', {}, ('Списание «Мой Класс» - это зачёт аванса: выберите в сценарии шаблон с оплатой '
                             '«предварительная оплата (аванс)», например «Зачёт аванса за услугу»')
    if not data.get('offset') and data.get('items_source') == 'Мой Класс' and template.get('payment_method') == 'full_payment' \
            and int(template.get('payment_type') if template.get('payment_type') is not None else 1) == 2:
        return 'error', {}, ('Оплата «Мой Класс» - это новые деньги, а шаблон сценария делает зачёт аванса. '
                             'Для оплат выберите шаблон предоплаты, для списаний - отдельную интеграцию с этапом «Новое списание»')
    if data.get('items_source') == 'RealtyCalendar':
        is_refund_doc = (template.get('operation') or 'sell') == 'sell_refund'
        if bool(data.get('refund')) != is_refund_doc:
            return 'error', {}, ('Возврат RealtyCalendar пробивается шаблоном с операцией «возврат прихода», а платёж - шаблоном прихода. '
                                 'Проверьте шаблон сценария и этап интеграции')
    if data.get('item_payment_method') in ('prepayment', 'advance') and template.get('payment_method') in ('full_prepayment', 'prepayment'):
        # Абонемент «Мой Класс» оплачен не полностью - это частичная предоплата, а не 100%.
        items = [{**i, 'payment_method': data['item_payment_method']} for i in items]
    total = round(sum(float(i.get('sum') or 0) for i in items), 2)

    source_company = dict(data.get('source_company') or {})
    if not source_company.get('inn') and cur is not None and job.get('company_id'):
        cur.execute(f'SELECT inn FROM {SCHEMA}.companies WHERE id = %s', (job['company_id'],))
        row = cur.fetchone()
        if row and row[0]:
            source_company['inn'] = row[0]
    customer = data.get('customer') or {}
    # ИНН покупателя касса принимает только из 10 или 12 цифр - иначе не передаём (и имя без ИНН тоже).
    customer_inn = re.sub(r'\D', '', str(customer.get('inn') or ''))
    if len(customer_inn) not in (10, 12):
        customer_inn = ''
    client = {k: v for k, v in {'email': customer.get('email') or template.get('default_email'),
                                'phone': customer.get('phone'),
                                'name': customer.get('name') if customer_inn else None,
                                'inn': customer_inn}.items() if v}
    correction_v4 = template.get('receipt_type') == 'correction' and template.get('protocol_version') != 'v5'
    # Чек коррекции v4 уходит без покупателя - почта/телефон не нужны.
    if not correction_v4 and not client.get('email') and not client.get('phone'):
        return 'error', {}, 'Нет почты или телефона покупателя - укажите почту по умолчанию в шаблоне действия'
    company = {k: v for k, v in {'inn': source_company.get('inn'), 'sno': data.get('taxation') or source_company.get('sno'),
                                 'payment_address': source_company.get('payment_address'),
                                 'email': source_company.get('email')}.items() if v}
    operation = document_operation(template)
    correction, err = correction_info(template, data)
    if err:
        return 'error', {}, err
    payment_type = template.get('payment_type')
    payments = [{'type': int(payment_type if payment_type is not None else 1), 'sum': total}]
    external_id = make_external_id(job, data, source_company.get('inn'), operation)
    if cur is not None:
        # Документ с этим номером уже упал в кассе (FAILED) - касса вернула бы его же. Новый номер с попыткой.
        cur.execute(f'''
            SELECT COUNT(*) FROM {SCHEMA}.automation_documents
            WHERE kassa_integration_id = %s AND external_id LIKE %s
        ''', (kassa['id'], f'{external_id}-old%'))
        previous = cur.fetchone()[0]
        if previous:
            external_id = f'{external_id}-r{previous + 1}'[:128]
    body = {
        'external_id': external_id,
        'timestamp': datetime.now(MSK).strftime('%d.%m.%Y %H:%M:%S'),
        'receipt': {'client': client, 'company': company, 'items': items, 'payments': payments, 'total': total}
    }
    if template.get('cashier_name'):
        body['receipt']['cashier'] = template['cashier_name']
    apply_agent(body['receipt'], template, data.get('agent'))
    if correction:
        r = body.pop('receipt')
        is_v5 = kassa['protocol_version'] == 'v5'
        # Место расчётов - всегда адрес выбранного магазина Екомкассы.
        payment_address = store_address(kassa).strip()
        if is_v5 and not payment_address:
            return 'error', {}, 'Нет места расчётов: у магазина Екомкассы не указан адрес - заполните его в Екомкассе'
        # v4: место расчётов касса берёт из регистрации, если его не передать.
        company = {**r['company'], **({'payment_address': payment_address} if payment_address else {})}
        default_email = str(template.get('default_email') or '').strip()
        if default_email and not company.get('email'):
            # Почта компании для чека коррекции - из «Почты по умолчанию» шаблона.
            company['email'] = default_email
        if is_v5 and not company.get('email'):
            # v5 требует почту продавца - берём из учётной записи владельца компании.
            owner_email = None
            if cur is not None and job.get('company_id'):
                cur.execute(f'''
                    SELECT u.email FROM {SCHEMA}.company_users cu
                    JOIN {SCHEMA}.roles ro ON ro.id = cu.role_id AND ro.slug = 'owner'
                    JOIN {SCHEMA}.app_users u ON u.id = cu.user_id
                    WHERE cu.company_id = %s AND cu.status = 'active' AND COALESCE(u.email, '') <> ''
                    ORDER BY cu.id LIMIT 1
                ''', (job['company_id'],))
                row = cur.fetchone()
                owner_email = row[0] if row else None
            if not owner_email:
                return 'error', {}, ('Нет почты продавца для чека коррекции v5 - укажите «Почту по умолчанию» '
                                     'в шаблоне или почту в профиле владельца компании')
            company['email'] = owner_email
        if kassa['protocol_version'] != 'v5':
            # АТОЛ v4 (ФФД 1.05): без позиций - только оплаты и суммы НДС по ставкам.
            rates = {'vat0': 0, 'vat5': 5, 'vat7': 7, 'vat10': 10, 'vat18': 18, 'vat20': 20, 'vat22': 22,
                     'vat105': 5, 'vat107': 7, 'vat110': 10, 'vat118': 18, 'vat120': 20, 'vat122': 22}
            vats: Dict[str, float] = {}
            for item in r['items']:
                vt = (item.get('vat') or {}).get('type') or 'none'
                rate = rates.get(vt, 0)
                amount = float(item.get('sum') or 0)
                vats[vt] = vats.get(vt, 0.0) + (round(amount * rate / (100 + rate), 2) if rate else 0.0)
            body['correction'] = {
                'company': company,
                'correction_info': correction,
                'payments': r['payments'],
                'vats': [{'type': vt, 'sum': round(v, 2)} for vt, v in vats.items()],
                **({'cashier': r['cashier']} if r.get('cashier') else {})
            }
        else:
            # АТОЛ v5 (ФФД 1.2): как обычный чек (покупатель, позиции, итог) + основание коррекции.
            body['correction'] = {**r, 'company': company, 'correction_info': correction}
    notify_url = callback_url(cur, job.get('company_id'))
    if notify_url:
        body['service'] = {'callback_url': notify_url}
    advance = round(sum(float(p['sum']) for p in payments if int(p['type']) == 2), 2)
    register_document(cur, job, scenario, kassa['id'], external_id, operation, total, advance, doc_kind='receipt')
    result, err = create_fiscal_receipt(kassa, operation, body)
    if not result:
        return 'error', {'request': body}, err
    receipt_uuid = str(result.get('uuid'))
    register_document(cur, job, scenario, kassa['id'], external_id, operation, total, advance, receipt_uuid, doc_kind='receipt')
    kind = 'чек коррекции' if correction else 'чек'
    return 'done', {'request': body, 'response': result, 'external_id': external_id}, (
        f"Екомкасса приняла {kind} #{receipt_uuid} на {total:.2f} ₽, шаблон «{template.get('name')}» "
        f"(статус кассы: {result.get('status')}, итог придёт уведомлением)"
    )


ACTIONS = {'create_order': create_order, 'create_receipt': create_receipt}

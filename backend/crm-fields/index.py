import json
import os
from typing import Any, Dict

import psycopg2

import amocrm_crm
import bitrix_crm
import moyklass_crm
import moyklass_api
import realtycalendar_crm
from auth_guard import guard

SCHEMA = 't_p83864310_fintech_payment_reco'
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}


def respond(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(payload, ensure_ascii=False, default=str),
        'isBase64Encoded': False
    }


def moyklass(method: str, body: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    '''
    «Мой Класс»: GET - поля (платёж, ученик + доп. признаки, абонемент, вид абонемента, группа, программа);
    POST {entity_id: ID платежа или списания, mapping} - какой чек получится по этому платежу.
    '''
    api_key = str(config.get('api_key') or '').strip()
    if method == 'GET':
        result, err = moyklass_crm.load_fields(api_key)
        if err:
            return respond(502, {'error': err})
        return respond(200, {'success': True, **result})

    offset = str(config.get('stage') or 'payment_new') == 'debit_new'
    payment_id = str(body.get('entity_id') or '').strip()
    if not payment_id.isdigit():
        return respond(200, {'success': False, 'error': 'Укажите номер (ID) платежа из «Мой Класс»'})
    token, err = moyklass_api.get_token(api_key)
    if not token:
        return respond(200, {'success': False, 'error': err})
    row, err = moyklass_api.get_payment(token, payment_id)
    if not row:
        return respond(200, {'success': False, 'error': f'Платёж #{payment_id} не найден: {err}'})
    obj = {'paymentId': row.get('id'), 'summa': row.get('summa'), 'date': row.get('date'), 'userId': row.get('userId'),
           'userSubscriptionId': row.get('userSubscriptionId') or (row.get('invoice') or {}).get('userSubscriptionId'),
           'optype': row.get('optype'), 'comment': row.get('comment'), 'paymentTypeId': row.get('paymentTypeId')}
    record, err = moyklass_crm.load_record(api_key, obj)
    if err:
        return respond(200, {'success': False, 'error': err})
    mapping = {**moyklass_crm.DEFAULT_MAPPING, **(body.get('mapping') or {})}
    data, build_error, note = moyklass_crm.build_data(record, mapping, offset)
    values = {k: moyklass_crm.resolve(record, mapping.get(k)) for k in
              ('order_id', 'amount', 'customer_email', 'customer_phone', 'customer_name', 'customer_inn')}
    kind = {'income': 'оплата', 'debit': 'списание', 'refund': 'возврат'}.get(str(row.get('optype')), row.get('optype'))
    expected = 'debit' if offset else 'income'
    mismatch = row.get('optype') and row.get('optype') != expected
    items = (data or {}).get('items') or []
    return respond(200, {
        'success': True,
        'title': f"{kind or 'платёж'} #{payment_id} от {moyklass_crm.human_date(str(row.get('date') or ''))}, ученик {record['user'].get('name') or ''}".strip(),
        'stage': kind,
        'stage_matches': not mismatch,
        'stage_note': (f'Это {kind}, а интеграция обрабатывает {"списания" if offset else "оплаты"} - по нему чек не создастся'
                       if mismatch else 'документ будет создан'),
        'values': values,
        'items': items,
        'name_limit': moyklass_crm.NAME_LIMIT,
        'full_names': moyklass_crm.full_item_names(record, mapping, offset) if items else [],
        'total': round(sum(i['sum'] for i in items), 2),
        'error': build_error or None,
        'note': note.lstrip(', ') or None,
    })


def realtycalendar(method: str, body: Dict[str, Any], config: Dict[str, Any], integration_id: int, company_id: int) -> Dict[str, Any]:
    '''
    RealtyCalendar: GET - поля (бронь, гость, объект, платёж);
    POST {entity_id: ID платежа (необязательно), mapping} - чек по платежу, уже полученному вебхуком
    (без номера - последний полученный). В API РК не ходим - бронь берём из сохранённого вебхука.
    '''
    if method == 'GET':
        return respond(200, {'success': True, **realtycalendar_crm.load_fields()})
    refund = str(config.get('stage') or 'income') == 'refund'
    pay_id = str(body.get('entity_id') or '').strip()
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        cur.execute(f'''
            SELECT payment_id, raw_data, status FROM {SCHEMA}.webhook_payments
            WHERE integration_id = %s AND company_id = %s AND removed_at IS NULL {'AND payment_id = %s' if pay_id else ''}
            ORDER BY created_at DESC LIMIT 1
        ''', (integration_id, company_id, pay_id) if pay_id else (integration_id, company_id))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return respond(200, {'success': False, 'error': (
            f'Платёж #{pay_id} ещё не приходил вебхуком в эту интеграцию' if pay_id else
            'Вебхуков с платежами ещё не было - добавьте платёж в бронь RealtyCalendar и нажмите «Проверить» снова')})
    raw = row[1] if isinstance(row[1], dict) else json.loads(row[1] or '{}')
    record = realtycalendar_crm.record_from_raw(raw)
    mapping = {**realtycalendar_crm.DEFAULT_MAPPING, **(body.get('mapping') or {})}
    data, build_error, note = realtycalendar_crm.build_data(record, mapping, refund)
    values = {k: realtycalendar_crm.resolve(record, mapping.get(k)) for k in
              ('order_id', 'amount', 'customer_email', 'customer_phone', 'customer_name', 'customer_inn')}
    booking = record.get('booking') or {}
    items = (data or {}).get('items') or []
    return respond(200, {
        'success': True,
        'title': (f"{'возврат' if refund else 'платёж'} #{row[0]} по брони #{booking.get('id')}, "
                  f"{realtycalendar_crm.human_date(str(booking.get('begin_date') or ''))}–{realtycalendar_crm.human_date(str(booking.get('end_date') or ''))}, "
                  f"гость {(record.get('client') or {}).get('fio') or '—'}"),
        'stage_matches': True,
        'stage_note': 'документ будет создан',
        'values': values,
        'items': items,
        'name_limit': realtycalendar_crm.NAME_LIMIT,
        'full_names': realtycalendar_crm.full_item_names(record, mapping) if items else [],
        'total': round(sum(i['sum'] for i in items), 2),
        'error': build_error or None,
        'note': note.lstrip(', ') or None,
    })


def bitrix_categories(params: Dict[str, Any], company_id: int, integration_id: Any) -> Dict[str, Any]:
    '''Воронки сделок портала Битрикс24 - по вебхуку из формы или по сохранённой интеграции.'''
    webhook_url = str(params.get('webhook_url') or '').strip()
    if not webhook_url and integration_id:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        try:
            cur.execute(f'SELECT config FROM {SCHEMA}.user_integrations WHERE id = %s AND company_id = %s',
                        (integration_id, company_id))
            row = cur.fetchone()
        finally:
            cur.close()
            conn.close()
        config = (json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})) if row else {}
        webhook_url = str(config.get('webhook_url') or '')
    if not webhook_url:
        return respond(200, {'success': False, 'error': 'Сначала укажите входящий вебхук Битрикс24'})
    result, err = bitrix_crm.call(webhook_url, 'crm.category.list', {'entityTypeId': 2})
    if err:
        return respond(200, {'success': False, 'error': err})
    raw = result.get('categories') if isinstance(result, dict) else result
    categories = [{'id': '0', 'name': 'Общая воронка'}]
    for c in raw or []:
        if isinstance(c, dict) and str(c.get('id')) != '0':
            categories.append({'id': str(c.get('id')), 'name': c.get('name') or f"Воронка {c.get('id')}"})
    return respond(200, {'success': True, 'categories': categories})


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Поля CRM для настройки сценария автоматизации (Битрикс24 и «Мой Класс»).
    GET ?company_id=&integration_id= - поля сделок, лидов, контактов, компаний и стадии воронок
    GET ?company_id=&categories=1&webhook_url= (или &integration_id=) - воронки сделок Битрикс24
    POST {company_id, integration_id, entity: deal|lead, entity_id, mapping} - проверка сопоставления
         на реальной сделке/лиде: какие значения подставятся и какой получится чек
    '''
    denied = guard(event)
    if denied:
        return denied

    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    params = event.get('queryStringParameters') or {}
    body = json.loads(event.get('body') or '{}') if method == 'POST' else {}
    company_id = params.get('company_id') or body.get('company_id')
    integration_id = params.get('integration_id') or body.get('integration_id')
    if method == 'GET' and params.get('categories') == '1' and company_id:
        return bitrix_categories(params, int(company_id), integration_id)
    if not company_id or not integration_id:
        return respond(400, {'error': 'company_id и integration_id обязательны'})

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        cur.execute(f'''
            SELECT p.slug, ui.config FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            WHERE ui.id = %s AND ui.company_id = %s
        ''', (integration_id, company_id))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return respond(404, {'error': 'Интеграция не найдена'})
    slug, config = row
    config = json.loads(config) if isinstance(config, str) else (config or {})
    if slug == 'moyklass':
        return moyklass(method, body, config)
    if slug == 'realtycalendar':
        return realtycalendar(method, body, config, int(integration_id), int(company_id))
    if slug not in ('bitrix24', 'amocrm'):
        return respond(400, {'error': 'Загрузка полей доступна для Битрикс24, AmoCRM и «Мой Класс»'})
    amo = slug == 'amocrm'
    webhook_url = config.get('webhook_url', '')

    if method == 'GET':
        result, err = amocrm_crm.load_fields(config) if amo else bitrix_crm.load_fields(webhook_url)
        if err:
            return respond(502, {'error': err})
        return respond(200, {'success': True, **result})

    if method == 'POST':
        entity = 'deal' if amo else (body.get('entity') or 'deal')
        mapping = {**bitrix_crm.DEFAULT_MAPPING, **(body.get('mapping') or {}), 'entity': entity}
        record, err = (amocrm_crm.load_record(config, body.get('entity_id')) if amo
                       else bitrix_crm.load_record(webhook_url, entity, body.get('entity_id')))
        if err:
            return respond(200, {'success': False, 'error': err})
        refs = {k: mapping.get(k) for k in ('order_id', 'amount', 'customer_email', 'customer_phone',
                                              'customer_name', 'customer_inn', 'agent_supplier_name',
                                              'agent_supplier_inn')}
        values = {k: bitrix_crm.resolve(record, entity, ref) for k, ref in refs.items()}
        values['agent_supplier_phones'] = ', '.join(bitrix_crm.resolve_all(record, entity, mapping.get('agent_supplier_phones'))) or None
        main = record[entity]
        condition_ok, condition_value = bitrix_crm.condition_check(mapping, entity, record)
        data, build_error, note = bitrix_crm.build_data(record, entity, mapping)
        full_names = bitrix_crm.full_item_names(record, entity, mapping)
        return respond(200, {
            'success': True,
            'title': main.get('TITLE'),
            'stage': main.get(bitrix_crm.STAGE_FIELD[entity]),
            'stage_matches': bitrix_crm.stage_matches(mapping, entity, main),
            'condition_matches': condition_ok,
            'condition_value': condition_value or None,
            'has_contact': bool(record.get('contact')),
            'has_company': bool(record.get('company')),
            'products_count': len(record.get('products') or []),
            'values': values,
            'items': (data or {}).get('items') or [],
            'name_limit': bitrix_crm.NAME_LIMIT,
            'full_names': full_names,
            'total': round(sum(i['sum'] for i in (data or {}).get('items') or []), 2),
            'error': build_error or None,
            'note': note.lstrip(', ') or None,
        })

    return respond(405, {'error': 'Method not allowed'})

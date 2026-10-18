import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import psycopg2

from alfabank_api import api_base, payment_way, ssl_context, _rub
from auth_guard import guard

SCHEMA = 't_p83864310_fintech_payment_reco'
PAGE_SIZE = 200

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id, X-Service-Sign, X-Cron-Token, X-User-Id, X-Auth-Token',
    'Access-Control-Max-Age': '86400'
}

# Статус документа в окне загрузки -> состояния заказа Альфа-Банка.
# «Оплачено» - списанные заказы (в т.ч. позже возвращённые: оплата всё равно была).
STATUS_STATES = {
    'paid': ['DEPOSITED', 'REFUNDED'],
    'refunded': ['REFUNDED'],
}


def reply(code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {'statusCode': code, 'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
            'body': json.dumps(payload, ensure_ascii=False, default=str), 'isBase64Encoded': False}


def alfa_date(value: str) -> str:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).strftime('%Y%m%d%H%M%S')


def fetch_page(config: Dict[str, Any], date_from: str, date_to: str, states: List[str],
               page: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    '''getLastOrdersForMerchants.do: заказы магазина за период, постранично.'''
    form: Dict[str, str] = {
        'language': 'ru', 'page': str(page), 'size': str(PAGE_SIZE),
        'from': alfa_date(date_from), 'to': alfa_date(date_to),
        'transactionStates': ','.join(states), 'merchants': '', 'searchByCreatedDate': 'false',
    }
    if config.get('token'):
        form['token'] = config['token']
    else:
        form['userName'] = config.get('user_name') or ''
        form['password'] = config.get('password') or ''
    req = urllib.request.Request(
        f'{api_base(config)}/getLastOrdersForMerchants.do',
        data=urllib.parse.urlencode(form).encode('utf-8'),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl_context()) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return None, f'Альфа-Банк ответил ошибкой {e.code}'
    except Exception as e:
        return None, f'Не удалось связаться с Альфа-Банком: {str(e)[:150]}'
    error_code = str(data.get('errorCode') if data.get('errorCode') is not None else '0')
    if error_code not in ('0', ''):
        message = data.get('errorMessage') or f'ошибка {error_code}'
        if error_code in ('5', '7'):
            message += ' - возможно, банк не включил магазину выгрузку списка заказов, напишите в поддержку эквайринга'
        return None, f'Альфа-Банк: {message}'
    return data, None


def md_order_of(order: Dict[str, Any]) -> Optional[str]:
    for attr in order.get('attributes') or []:
        if attr.get('name') == 'mdOrder' and attr.get('value'):
            return str(attr['value'])
    return str(order.get('orderId') or order.get('mdOrder') or '') or None


def save_order(cur, integration_id: int, company_id: int, order: Dict[str, Any], statuses: List[str]) -> int:
    '''Заказ -> строки платежа (CONFIRMED и/или REFUNDED) в том же формате, что и уведомления банка.'''
    md_order = md_order_of(order)
    if not md_order:
        return 0
    info = order.get('paymentAmountInfo') or {}
    state = str(info.get('paymentState') or order.get('orderStatus') or '').upper()
    card = order.get('cardAuthInfo') or {}
    rows = []
    if 'paid' in statuses and state in ('DEPOSITED', 'REFUNDED', '2', '4'):
        rows.append(('CONFIRMED', 'deposited', _rub(info.get('depositedAmount') or order.get('amount'))))
    if 'refunded' in statuses and state in ('REFUNDED', '4'):
        rows.append(('REFUNDED', 'refunded', _rub(info.get('refundedAmount') or order.get('amount'))))
    inserted = 0
    for status, operation, amount in rows:
        cur.execute(f'''
            INSERT INTO {SCHEMA}.webhook_payments (
                integration_id, company_id, payment_id, terminal_key, amount, order_id, status, payment_status,
                error_code, customer_email, customer_phone, pan, card_type, exp_date, raw_data, payment_provider, origin
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s, %s, %s, %s, %s, 'manual')
            ON CONFLICT (integration_id, payment_id, status) DO NOTHING
            RETURNING id
        ''', (
            integration_id, company_id, md_order, order.get('terminalId'), amount, order.get('orderNumber'),
            status, operation, card.get('maskedPan') or card.get('pan'), card.get('paymentSystem'),
            card.get('expiration'), json.dumps({'order': order, 'source': 'backfill'}, ensure_ascii=False),
            payment_way(order, {})
        ))
        if cur.fetchone():
            inserted += 1
    return inserted


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Дозагрузка платежей интернет-эквайринга Альфа-Банка за период (getLastOrdersForMerchants).
    Body: company_id, integration_id, date_from, date_to (ISO), statuses (['paid','refunded']), page (с 0).
    Одна страница (до 200 заказов) за вызов; фронтенд повторяет с page+1, пока done=false.
    Returns: success, total, processed, inserted, next_page, done
    '''
    denied = guard(event)
    if denied:
        return denied
    if event.get('httpMethod') != 'POST':
        return reply(405, {'error': 'Method not allowed'})

    body = json.loads(event.get('body') or '{}') or {}
    company_id = body.get('company_id')
    integration_id = body.get('integration_id')
    date_from, date_to = body.get('date_from'), body.get('date_to')
    statuses = [s for s in (body.get('statuses') or ['paid']) if s in STATUS_STATES] or ['paid']
    page = max(0, int(body.get('page') or 0))
    if not company_id or not integration_id or not date_from or not date_to:
        return reply(400, {'error': 'company_id, integration_id, date_from, date_to обязательны'})
    try:
        alfa_date(date_from)
        alfa_date(date_to)
    except ValueError:
        return reply(400, {'error': 'Некорректный формат date_from/date_to'})

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        cur.execute(f'''
            SELECT ui.config FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            WHERE ui.id = %s AND ui.company_id = %s AND p.slug = 'alfabank' AND ui.status = 'active'
        ''', (integration_id, company_id))
        row = cur.fetchone()
        if not row:
            return reply(404, {'error': 'Активная интеграция Альфа-Банка не найдена'})
        config = row[0] if isinstance(row[0], dict) else json.loads(row[0] or '{}')

        states = sorted({st for s in statuses for st in STATUS_STATES[s]})
        data, error = fetch_page(config, date_from, date_to, states, page)
        if error:
            return reply(200, {'success': False, 'error': error})

        orders = data.get('orderStatuses') or []
        inserted = sum(save_order(cur, integration_id, company_id, o, statuses) for o in orders)
        cur.execute(f'UPDATE {SCHEMA}.user_integrations SET last_synced_at = NOW() WHERE id = %s', (integration_id,))
        conn.commit()

        total = int(data.get('totalCount') or 0)
        processed = page * PAGE_SIZE + len(orders)
        done = len(orders) < PAGE_SIZE or processed >= total
        return reply(200, {'success': True, 'total': max(total, processed), 'processed': processed,
                           'inserted': inserted, 'next_page': page + 1, 'done': done})
    finally:
        cur.close()
        conn.close()

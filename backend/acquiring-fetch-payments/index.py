import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import psycopg2

import alfabank_backfill
import cloudpayments_api
import tochka_acquiring_api
import yookassa_api
from auth_guard import guard, subscription_guard

SCHEMA = 't_p83864310_fintech_payment_reco'
PROVIDERS = ('alfabank', 'yookassa', 'tochka_acquiring', 'cloudpayments')
STATUSES = ('paid', 'refunded')
TOCHKA_UAPI = 'https://enter.tochka.com/uapi'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id, X-Service-Sign, X-Cron-Token, X-User-Id, X-Auth-Token',
    'Access-Control-Max-Age': '86400'
}

Row = Dict[str, Any]
Page = Tuple[List[Row], Optional[Dict[str, Any]], Optional[str]]


def reply(code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {'statusCode': code, 'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
            'body': json.dumps(payload, ensure_ascii=False, default=str), 'isBase64Encoded': False}


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)


def msk_date(value: str) -> date:
    return (parse_iso(value) + timedelta(hours=3)).date()


def _f(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


# ---------- ЮKassa: GET /v3/payments и /v3/refunds с курсором ----------

def yookassa_page(config: Dict[str, Any], date_from: str, date_to: str, statuses: List[str],
                  cursor: Dict[str, Any]) -> Page:
    phases = [p for p in ('payments', 'refunds') if (p == 'payments' and 'paid' in statuses)
              or (p == 'refunds' and 'refunded' in statuses)]
    phase = cursor.get('phase') or phases[0]
    query = {
        'created_at.gte': parse_iso(date_from).strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        'created_at.lte': parse_iso(date_to).strftime('%Y-%m-%dT%H:%M:%S.999Z'),
        'status': 'succeeded', 'limit': '100',
    }
    if cursor.get('next'):
        query['cursor'] = cursor['next']
    data, err, _ = yookassa_api.api_get(config, f'/{phase}?{urllib.parse.urlencode(query)}', timeout=15)
    if data is None:
        return [], None, err
    rows: List[Row] = []
    for obj in data.get('items') or []:
        if phase == 'payments':
            method = obj.get('payment_method') or {}
            card = method.get('card') or {}
            rows.append({
                'payment_id': str(obj.get('id')), 'status': 'CONFIRMED', 'payment_status': obj.get('status'),
                'amount': yookassa_api._amount(obj), 'order_id': yookassa_api._order_id(obj),
                'terminal_key': str(config.get('shop_id') or '')[:50] or None,
                'pan': f"{card.get('first6', '')}******{card.get('last4')}" if card.get('last4') else None,
                'card_type': str(card.get('card_type'))[:20] if card.get('card_type') else None,
                'provider': yookassa_api.payment_method_name(obj), 'raw': {'payment': obj},
            })
        else:
            rows.append({
                'payment_id': str(obj.get('payment_id')), 'status': 'REFUNDED', 'payment_status': obj.get('status'),
                'amount': yookassa_api._amount(obj), 'order_id': None,
                'terminal_key': str(config.get('shop_id') or '')[:50] or None,
                'pan': None, 'card_type': None, 'provider': None, 'raw': {'refund': obj},
            })
    if data.get('next_cursor'):
        return rows, {'phase': phase, 'next': data['next_cursor']}, None
    idx = phases.index(phase)
    return rows, ({'phase': phases[idx + 1]} if idx + 1 < len(phases) else None), None


# ---------- Точка: GET /acquiring/v1.0/payments по дням периода, постранично ----------

def tochka_get(path: str, token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    req = urllib.request.Request(f'{TOCHKA_UAPI}{path}', headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=20, context=tochka_acquiring_api.ssl_context()) as resp:
            return json.loads(resp.read().decode('utf-8')), None
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, ('Точка не дала доступ к операциям эквайринга: проверьте токен и право '
                          '«Интернет-эквайринг» (ReadAcquiringData)')
        return None, f'Точка ответила ошибкой {e.code}'
    except Exception as e:
        return None, f'Не удалось связаться с Точкой: {str(e)[:150]}'


def tochka_customer_code(config: Dict[str, Any], token: str) -> Tuple[Optional[str], Optional[str]]:
    code = str(config.get('customer_code') or '').strip()
    if code:
        return code, None
    data, err = tochka_get('/open-banking/v1.0/customers', token)
    if data is None:
        return None, err
    codes = [c.get('customerCode') for c in (data.get('Data') or {}).get('Customer', [])
             if c.get('customerType') == 'Business' and c.get('customerCode')]
    return (codes[0], None) if codes else (None, 'У токена нет доступа к бизнес-клиенту Точки')


def tochka_page(cur, company_id: int, config: Dict[str, Any], date_from: str, date_to: str,
                statuses: List[str], cursor: Dict[str, Any]) -> Page:
    token, token_err = tochka_acquiring_api.api_token(cur, company_id, config)
    if not token:
        return [], None, token_err or 'Нет токена Точки'
    code, err = tochka_customer_code(config, token)
    if not code:
        return [], None, err
    page = int(cursor.get('page') or 1)
    query = {'customerCode': code, 'fromDate': msk_date(date_from).isoformat(),
             'toDate': msk_date(date_to).isoformat(), 'page': str(page), 'perPage': '100'}
    if config.get('merchant_id'):
        query['merchantId'] = str(config['merchant_id'])
    data, err = tochka_get(f'/acquiring/v1.0/payments?{urllib.parse.urlencode(query)}', token)
    if data is None:
        return [], None, err
    ops = (data.get('Data') or {}).get('Operation') or []
    rows: List[Row] = []
    for op in ops:
        state = str(op.get('status') or '').upper()
        mapped = tochka_acquiring_api.STATUSES.get(state)
        wanted = []
        if 'paid' in statuses and mapped in ('CONFIRMED', 'REFUNDED'):
            wanted.append(('CONFIRMED', _f(op.get('amount'))))
        if 'refunded' in statuses and mapped == 'REFUNDED':
            wanted.append(('REFUNDED', _f(op.get('refundedAmount') or op.get('amount'))))
        cof = op.get('cof') or op.get('Cof') or {}
        client = op.get('client') or op.get('Client') or {}
        for status, amount in wanted:
            rows.append({
                'payment_id': str(op.get('operationId')), 'status': status, 'payment_status': op.get('status'),
                'amount': amount, 'order_id': op.get('paymentLinkId'), 'terminal_key': op.get('merchantId'),
                'pan': op.get('maskedPan') or cof.get('maskedPan'), 'card_type': op.get('cardType') or cof.get('cardType'),
                'email': client.get('email'), 'phone': client.get('phone'),
                'provider': tochka_acquiring_api.PAYMENT_WAYS.get(str(op.get('paymentType') or ''), op.get('paymentType')),
                'raw': {'operation': {k: v for k, v in op.items() if k != 'Items'}},
            })
    total_pages = int(((data.get('Meta') or {}).get('totalPages')) or 0)
    has_more = (page < total_pages) if total_pages else len(ops) >= 100
    return rows, ({'page': page + 1} if has_more else None), None


# ---------- CloudPayments: POST /payments/list по одному дню ----------

def cloudpayments_page(config: Dict[str, Any], date_from: str, date_to: str, statuses: List[str],
                       cursor: Dict[str, Any]) -> Page:
    start, end = msk_date(date_from), msk_date(date_to)
    day = date.fromisoformat(cursor['day']) if cursor.get('day') else start
    resp, err, _ = cloudpayments_api.api_post(config, '/payments/list',
                                              {'Date': day.isoformat(), 'TimeZone': 'MSK'}, timeout=20)
    if resp is None:
        return [], None, err
    if not resp.get('Success'):
        return [], None, f"CloudPayments: {resp.get('Message') or 'не удалось получить список платежей'}"
    rows: List[Row] = []
    for tx in resp.get('Model') or []:
        state = str(tx.get('Status') or '')
        if state not in ('Completed', 'Refunded'):
            continue
        tx_id = str(tx.get('TransactionId'))
        base = {
            'payment_id': tx_id, 'payment_status': state,
            'order_id': str(tx.get('InvoiceId'))[:100] if tx.get('InvoiceId') else None,
            'terminal_key': str(config.get('public_id') or '')[:100] or None,
            'pan': f"{tx.get('CardFirstSix') or ''}******{tx.get('CardLastFour')}" if tx.get('CardLastFour') else None,
            'card_type': str(tx.get('CardType'))[:20] if tx.get('CardType') else None,
            'email': (str(tx.get('Email'))[:255] if tx.get('Email') else None),
            'provider': cloudpayments_api.payment_method_name(tx), 'raw': {'transaction': tx},
        }
        if 'paid' in statuses:
            rows.append({**base, 'status': 'CONFIRMED', 'amount': cloudpayments_api._rub(tx.get('Amount'))})
        if 'refunded' in statuses and state == 'Refunded':
            rows.append({**base, 'status': 'REFUNDED',
                         'amount': cloudpayments_api._rub(tx.get('RefundAmount') or tx.get('Amount'))})
    nxt = day + timedelta(days=1)
    return rows, ({'day': nxt.isoformat()} if nxt <= end else None), None


def save_rows(cur, integration_id: int, company_id: int, rows: List[Row]) -> int:
    '''Платежи - в том же формате, что и из уведомлений; уже загруженные не дублируются.'''
    inserted = 0
    for r in rows:
        if not r.get('payment_id') or r['payment_id'] == 'None':
            continue
        cur.execute(f'''
            INSERT INTO {SCHEMA}.webhook_payments (
                integration_id, company_id, payment_id, terminal_key, amount, order_id, status, payment_status,
                error_code, customer_email, customer_phone, pan, card_type, exp_date, raw_data, payment_provider, origin
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, NULL, %s, %s, 'manual')
            ON CONFLICT (integration_id, payment_id, status) DO NOTHING
            RETURNING id
        ''', (
            integration_id, company_id, r['payment_id'], r.get('terminal_key'), r.get('amount') or 0,
            r.get('order_id'), r['status'], (str(r.get('payment_status') or '')[:50] or None),
            r.get('email'), r.get('phone'), r.get('pan'), r.get('card_type'),
            json.dumps({**r.get('raw', {}), 'source': 'backfill'}, ensure_ascii=False, default=str),
            (str(r['provider'])[:100] if r.get('provider') else None),
        ))
        if cur.fetchone():
            inserted += 1
    return inserted


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Дозагрузка платежей интернет-эквайринга за период: Альфа-Банк, ЮKassa, Точка (интернет-эквайринг), CloudPayments.
    Body: company_id, integration_id, date_from, date_to (ISO), statuses (['paid','refunded']), cursor (из прошлого ответа).
    Одна страница за вызов; фронтенд повторяет с next_cursor, пока done=false.
    Returns: success, found, inserted, next_cursor, done
    '''
    denied = guard(event)
    if denied:
        return denied
    blocked = subscription_guard(event)
    if blocked:
        return blocked
    if event.get('httpMethod') != 'POST':
        return reply(405, {'error': 'Method not allowed'})

    body = json.loads(event.get('body') or '{}') or {}
    company_id = body.get('company_id')
    integration_id = body.get('integration_id')
    date_from, date_to = body.get('date_from'), body.get('date_to')
    statuses = [s for s in (body.get('statuses') or ['paid']) if s in STATUSES] or ['paid']
    cursor = body.get('cursor') if isinstance(body.get('cursor'), dict) else {}
    if not company_id or not integration_id or not date_from or not date_to:
        return reply(400, {'error': 'company_id, integration_id, date_from, date_to обязательны'})
    try:
        if parse_iso(date_from) > parse_iso(date_to):
            return reply(400, {'error': 'Начало периода позже конца'})
    except ValueError:
        return reply(400, {'error': 'Некорректный формат date_from/date_to'})

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        cur.execute(f'''
            SELECT ui.config, p.slug FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            WHERE ui.id = %s AND ui.company_id = %s AND ui.status = 'active'
        ''', (integration_id, company_id))
        row = cur.fetchone()
        if not row or row[1] not in PROVIDERS:
            return reply(404, {'error': 'Активная интеграция эквайринга не найдена'})
        config = row[0] if isinstance(row[0], dict) else json.loads(row[0] or '{}')
        slug = row[1]

        if slug == 'alfabank':
            page = int(cursor.get('page') or 0)
            states = sorted({st for s in statuses for st in alfabank_backfill.STATUS_STATES[s]})
            data, err = alfabank_backfill.fetch_page(config, date_from, date_to, states, page)
            if err:
                return reply(200, {'success': False, 'error': err})
            orders = data.get('orderStatuses') or []
            inserted = sum(alfabank_backfill.save_order(cur, integration_id, company_id, o, statuses) for o in orders)
            cur.execute(f'UPDATE {SCHEMA}.user_integrations SET last_synced_at = NOW() WHERE id = %s', (integration_id,))
            conn.commit()
            total = int(data.get('totalCount') or 0)
            processed = page * alfabank_backfill.PAGE_SIZE + len(orders)
            done = len(orders) < alfabank_backfill.PAGE_SIZE or processed >= total
            return reply(200, {'success': True, 'found': len(orders), 'inserted': inserted,
                               'next_cursor': None if done else {'page': page + 1}, 'done': done})
        if slug == 'yookassa':
            rows, next_cursor, err = yookassa_page(config, date_from, date_to, statuses, cursor)
        elif slug == 'tochka_acquiring':
            rows, next_cursor, err = tochka_page(cur, company_id, config, date_from, date_to, statuses, cursor)
            conn.commit()
        else:
            rows, next_cursor, err = cloudpayments_page(config, date_from, date_to, statuses, cursor)
        if err:
            return reply(200, {'success': False, 'error': err})

        inserted = save_rows(cur, integration_id, company_id, rows)
        cur.execute(f'UPDATE {SCHEMA}.user_integrations SET last_synced_at = NOW() WHERE id = %s', (integration_id,))
        conn.commit()
        return reply(200, {'success': True, 'found': len(rows), 'inserted': inserted,
                           'next_cursor': next_cursor, 'done': next_cursor is None})
    finally:
        cur.close()
        conn.close()

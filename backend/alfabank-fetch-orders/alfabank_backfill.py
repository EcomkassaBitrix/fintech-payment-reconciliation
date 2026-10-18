'''Альфа-Банк: заказы за период (getLastOrdersForMerchants) для дозагрузки.'''
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from alfabank_api import api_base, payment_way, ssl_context, _rub

SCHEMA = 't_p83864310_fintech_payment_reco'
PAGE_SIZE = 200

# Статус документа в окне загрузки -> состояния заказа Альфа-Банка.
# «Оплачено» - списанные заказы (в т.ч. позже возвращённые: оплата всё равно была).
STATUS_STATES = {
    'paid': ['DEPOSITED', 'REFUNDED'],
    'refunded': ['REFUNDED'],
}


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

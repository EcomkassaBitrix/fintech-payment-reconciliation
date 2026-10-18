'''
Интернет-эквайринг Точки (платёжные ссылки): вебхук acquiringInternetPayment.

Вебхук - «голая» строка JWT (Content-Type: text/plain), подписанная RS256 ключом Точки.
Подпись проверяем публичным ключом банка (без сторонних библиотек: RSA PKCS#1 v1.5 + SHA-256).
В вебхуке нет состава заказа - по operationId запрашиваем Get Payment Operation Info
(GET /acquiring/v1.0/payments/{operationId}, токен JWT клиента): там Items - корзина для чека.
'''
import base64
import hashlib
import json
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from russian_ca import RUSSIAN_TRUSTED_CA
import tochka_oauth

SCHEMA = 't_p83864310_fintech_payment_reco'
API_BASE = 'https://enter.tochka.com/uapi/acquiring/v1.0'

# Публичный ключ Точка Банка для подписи вебхуков (https://enter.tochka.com/doc/openapi/static/keys/public).
TOCHKA_PUBLIC_KEY = {
    'kty': 'RSA', 'e': 'AQAB',
    'n': ('rwm77av7GIttq-JF1itEgLCGEZW_zz16RlUQVYlLbJtyRSu61fCec_rroP6PxjXU2uLzUOaGaLgAPeUZAJrGuVp9nryKgbZceHckdHDYgJd9TsdJ1MYUsXaOb9joN9vmsCscBx1lwSlFQyNQsHUsrjuDk-opf6RCuazRQ9gkoDCX70HV8WBMFoVm-YWQKJHZEaIQxg_DU4gMFyKRkDGKsYKA0POL-UgWA1qkg6nHY5BOMKaqxbc5ky87muWB5nNk4mfmsckyFv9j1gBiXLKekA_y4UwG2o1pbOLpJS3bP_c95rm4M9ZBmGXqfOQhbjz8z-s9C11i-jmOQ2ByohS-ST3E5sqBzIsxxrxyQDTw--bZNhzpbciyYW4GfkkqyeYoOPd_84jPTBDKQXssvj8ZOj2XboS77tvEO1n1WlwUzh8HPCJod5_fEgSXuozpJtOggXBv0C2ps7yXlDZf-7Jar0UYc_NJEHJF-xShlqd6Q3sVL02PhSCM-ibn9DN9BKmD'),
}

STATUSES = {
    'APPROVED': 'CONFIRMED',
    'AUTHORIZED': 'AUTHORIZED',
    'REFUNDED': 'REFUNDED',
    'REFUNDED_PARTIALLY': 'REFUNDED',
    'ON-REFUND': 'REFUNDED',
    'EXPIRED': 'REJECTED',
}
NOTIFY_KEYS = {
    'AUTHORIZED': 'notify_on_authorized', 'CONFIRMED': 'notify_on_confirmed',
    'REJECTED': 'notify_on_rejected', 'REFUNDED': 'notify_on_refunded',
}
PAYMENT_WAYS = {'card': 'Карта', 'sbp': 'СБП', 'dolyame': 'Долями', 'tinkoff': 'T-Pay', 'digitalRuble': 'Цифровой рубль'}
PAYMENT_OBJECTS = {'goods': 'commodity', 'service': 'service', 'work': 'job'}
MEASURES = {'шт.': 'шт', 'г.': 'г', 'кг.': 'кг', 'л.': 'л', 'мл.': 'мл', 'м.': 'м', 'ч.': 'ч', 'дн.': 'сут'}

_ctx: Dict[str, ssl.SSLContext] = {}


def ssl_context() -> ssl.SSLContext:
    if 'ctx' not in _ctx:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cadata=RUSSIAN_TRUSTED_CA)
        _ctx['ctx'] = ctx
    return _ctx['ctx']


def _b64d(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def verify_jwt(token: str) -> Optional[Dict[str, Any]]:
    '''Проверка подписи RS256 публичным ключом Точки. Подпись неверна - None.'''
    try:
        header_b64, payload_b64, sig_b64 = token.strip().split('.')
        header = json.loads(_b64d(header_b64))
        if header.get('alg') != 'RS256':
            return None
        n = int.from_bytes(_b64d(TOCHKA_PUBLIC_KEY['n']), 'big')
        e = int.from_bytes(_b64d(TOCHKA_PUBLIC_KEY['e']), 'big')
        k = (n.bit_length() + 7) // 8
        em = pow(int.from_bytes(_b64d(sig_b64), 'big'), e, n).to_bytes(k, 'big')
        digest = hashlib.sha256(f'{header_b64}.{payload_b64}'.encode('ascii')).digest()
        prefix = bytes.fromhex('3031300d060960864801650304020105000420')
        expected = b'\x00\x01' + b'\xff' * (k - 3 - len(prefix) - len(digest)) + b'\x00' + prefix + digest
        if em != expected:
            return None
        return json.loads(_b64d(payload_b64))
    except Exception:
        return None


def api_token(cur, company_id: int, config: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    '''Токен для API эквайринга: JWT из настроек или доступ компании, выданный через вход в Точку (OAuth).'''
    if config.get('auth_method') == 'oauth':
        token, err = tochka_oauth.get_access_token(cur, company_id)
        return token or '', err
    return str(config.get('api_token') or ''), None


def _token(cur, company_id: int, config: Dict[str, Any]) -> Tuple[str, Optional[str]]:
    return api_token(cur, company_id, config)


def get_operation(api_token: str, token_error: Optional[str], operation_id: str = '', timeout: float = 10
                  ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    '''Get Payment Operation Info: статус, способ оплаты, покупатель и корзина (Items).'''
    if not api_token:
        return None, token_error or 'Нет токена Точки'
    req = urllib.request.Request(f'{API_BASE}/payments/{operation_id}',
                                 headers={'Authorization': f'Bearer {api_token}'})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, 'Точка не дала доступ к операции: проверьте токен и право «Интернет-эквайринг» (ReadAcquiringData)'
        return None, f'Точка ответила ошибкой {e.code}'
    except Exception as e:
        return None, f'Не удалось связаться с Точкой: {str(e)[:150]}'
    ops = ((data or {}).get('Data') or {}).get('Operation') or []
    if not ops:
        return None, 'Точка не нашла операцию'
    return ops[0], None


def convert_items(op: Dict[str, Any]) -> List[Dict[str, Any]]:
    '''Items операции Точки -> наш формат корзины (как у Т-Банка): цена за единицу, сумма позиции.'''
    items = []
    for it in op.get('Items') or []:
        if not isinstance(it, dict):
            continue
        price = round(float(it.get('amount') or 0), 2)
        quantity = float(it.get('quantity') or 1)
        supplier = it.get('Supplier') or op.get('Supplier')
        item = {
            'name': it.get('name') or 'Товар',
            'price': price,
            'quantity': quantity,
            'amount': round(price * quantity, 2),
            'tax': it.get('vatType') or 'none',
            'payment_method': it.get('paymentMethod') or 'full_payment',
            'payment_object': PAYMENT_OBJECTS.get(it.get('paymentObject') or 'goods', 'commodity'),
            'measurement_unit': MEASURES.get(it.get('measure') or 'шт.', (it.get('measure') or 'шт').rstrip('.')),
        }
        if isinstance(supplier, dict) and supplier.get('taxCode'):
            item['supplier_info'] = {'Name': supplier.get('name'), 'Inn': supplier.get('taxCode'),
                                     'Phones': [supplier['phone']] if supplier.get('phone') else []}
        items.append(item)
    return items


def save_cart(cur, integration_id: int, company_id: int, operation_id: str, op: Dict[str, Any]) -> int:
    items = convert_items(op)
    client = op.get('Client') or {}
    receipt = {'Email': client.get('email'), 'Phone': client.get('phone'), 'Customer': client.get('name'),
               'Taxation': op.get('taxSystemCode'), 'operation': {k: v for k, v in op.items() if k != 'Items'}}
    total = round(sum(i['amount'] for i in items), 2)
    cur.execute(f'''
        INSERT INTO {SCHEMA}.payment_carts
            (company_id, integration_id, payment_id, order_id, source, items, receipt, items_total, fiscal_data,
             fiscalized, receipt_id)
        VALUES (%s, %s, %s, %s, 'tochka_acquiring', %s, %s, %s, '{{}}'::jsonb, false, NULL)
        ON CONFLICT (integration_id, payment_id) DO UPDATE SET
            items = EXCLUDED.items, receipt = EXCLUDED.receipt, items_total = EXCLUDED.items_total,
            order_id = COALESCE(EXCLUDED.order_id, payment_carts.order_id), updated_at = NOW()
    ''', (company_id, integration_id, operation_id, op.get('paymentLinkId'),
          json.dumps(items, ensure_ascii=False), json.dumps(receipt, ensure_ascii=False), total))
    return len(items)


def extract_jwt(raw_body: str, webhook_data: Any) -> str:
    '''Тело вебхука - строка JWT (text/plain); на всякий случай поддерживаем и JSON-обёртку.'''
    body = (raw_body or '').strip().strip('"')
    if body.count('.') == 2 and body.startswith('eyJ'):
        return body
    if isinstance(webhook_data, dict):
        for key in ('token', 'jwt', 'data'):
            value = webhook_data.get(key)
            if isinstance(value, str) and value.count('.') == 2:
                return value
    return ''


def process(cur, integration_id: int, company_id: int, config: Dict[str, Any],
            webhook_settings: Dict[str, Any], raw_body: str, webhook_data: Any
            ) -> Tuple[bool, Optional[int], Optional[str], Dict[str, Any]]:
    '''
    Вебхук Точки: проверка подписи, статус, загрузка операции с корзиной, сохранение платежа.
    Returns: (подпись_верна, webhook_payment_id, ошибка, расшифрованные данные вебхука)
    '''
    token = extract_jwt(raw_body, webhook_data)
    data = verify_jwt(token) if token else None
    if data is None:
        return False, None, 'Неверная подпись вебхука Точки', {}
    if data.get('webhookType') and data.get('webhookType') != 'acquiringInternetPayment':
        return True, None, None, data
    merchant = str(config.get('merchant_id') or '').strip()
    if merchant and data.get('merchantId') and str(data['merchantId']) != merchant:
        return True, None, None, data

    operation_id = str(data.get('operationId') or '').strip()
    if not operation_id:
        return True, None, 'В вебхуке нет operationId', data
    status = STATUSES.get(str(data.get('status') or '').upper())
    if not status:
        return True, None, None, data
    notify_key = NOTIFY_KEYS.get(status)
    if notify_key and not webhook_settings.get(notify_key, True):
        return True, None, None, data

    op, op_error = get_operation(*_token(cur, company_id, config), operation_id)
    if op:
        save_cart(cur, integration_id, company_id, operation_id, op)
    client = (op or {}).get('Client') or {}
    cof = (op or {}).get('CofToken') or {}
    amount = float(data.get('amount') or (op or {}).get('amount') or 0)
    raw = {'webhook': data, 'operation': op, 'operation_error': op_error}
    cur.execute(f'''
        INSERT INTO {SCHEMA}.webhook_payments (
            integration_id, company_id, payment_id, terminal_key, amount, order_id, status, payment_status,
            error_code, customer_email, customer_phone, pan, card_type, exp_date, raw_data, payment_provider, origin
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s, NULL, %s, %s, 'automation')
        ON CONFLICT (integration_id, payment_id, status) DO NOTHING
        RETURNING id
    ''', (
        integration_id, company_id, operation_id, data.get('merchantId'), round(amount, 2),
        data.get('paymentLinkId') or (op or {}).get('paymentLinkId'), status, data.get('status'),
        client.get('email'), client.get('phone'),
        data.get('maskedPan') or cof.get('maskedPan'), data.get('cardType') or cof.get('cardType'),
        json.dumps(raw, ensure_ascii=False),
        PAYMENT_WAYS.get(str(data.get('paymentType') or ''), data.get('paymentType'))
    ))
    row = cur.fetchone()
    # Корзину не получили - платёж всё равно принят: автоматизация дозапросит её у банка.
    return True, (row[0] if row else None), None, data

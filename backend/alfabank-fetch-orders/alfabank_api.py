'''
Интернет-эквайринг Альфа-Банка (платёжный шлюз alfa.rbsuat.com / payment.alfabank.ru).

Уведомление (callback) приходит GET или POST с параметрами:
  mdOrder, orderNumber, operation (approved/deposited/reversed/refunded/declinedByTimeout...),
  status (1 - успех, 0 - ошибка), checksum (если включены уведомления с контрольной суммой).
Состава заказа в уведомлении нет - по mdOrder запрашиваем getOrderStatusExtended.do,
в ответе orderBundle.cartItems.items - корзина, по ней пробиваем чек.

Контрольная сумма (симметричный ключ): параметры без checksum и sign_alias,
сортировка по имени, строка "имя;значение;...;" -> HMAC-SHA256 -> HEX в верхнем регистре.
'''
import hashlib
import hmac
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from russian_ca import RUSSIAN_TRUSTED_CA

SCHEMA = 't_p83864310_fintech_payment_reco'

API_URLS = {
    'test': 'https://alfa.rbsuat.com/payment/rest',
    'prod': 'https://payment.alfabank.ru/payment/rest',
    'prod_pay': 'https://pay.alfabank.ru/payment/rest',
}

# operation + status -> статус платежа в нашем формате (как у Т-Банка).
OPERATION_STATUS = {
    ('approved', '1'): 'AUTHORIZED',
    ('deposited', '1'): 'CONFIRMED',
    ('approved', '0'): 'REJECTED',
    ('deposited', '0'): 'REJECTED',
    ('declinedbytimeout', '1'): 'REJECTED',
    ('declinedbytimeout', '0'): 'REJECTED',
    ('declinedcardpresent', '1'): 'REJECTED',
    ('declinedcardpresent', '0'): 'REJECTED',
    ('reversed', '1'): 'CANCELED',
    ('refunded', '1'): 'REFUNDED',
}

NOTIFY_KEYS = {
    'AUTHORIZED': 'notify_on_authorized',
    'CONFIRMED': 'notify_on_confirmed',
    'REJECTED': 'notify_on_rejected',
    'REFUNDED': 'notify_on_refunded',
    'CANCELED': 'notify_on_canceled',
}

# taxType Альфа-Банка -> ставка НДС кассы (АТОЛ).
TAX_TYPES = {
    0: 'none', 1: 'vat0', 2: 'vat10', 3: 'vat18', 4: 'vat110', 5: 'vat118',
    6: 'vat20', 7: 'vat120', 10: 'vat5', 11: 'vat105', 12: 'vat7', 13: 'vat107',
    14: 'vat22', 15: 'vat122',
}

PAYMENT_METHODS = {
    1: 'full_prepayment', 2: 'prepayment', 3: 'advance', 4: 'full_payment',
    5: 'partial_payment', 6: 'credit', 7: 'credit_payment',
}

PAYMENT_OBJECTS = {
    1: 'commodity', 2: 'excise', 3: 'job', 4: 'service', 5: 'gambling_bet', 6: 'gambling_prize',
    7: 'lottery', 8: 'lottery_prize', 9: 'intellectual_activity', 10: 'payment', 11: 'agent_commission',
    12: 'composite', 13: 'another',
}


_ssl_context: Dict[str, ssl.SSLContext] = {}


def ssl_context() -> ssl.SSLContext:
    '''Серверы Альфа-Банка подписаны сертификатами Минцифры - добавляем их к системным.'''
    if 'ctx' not in _ssl_context:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cadata=RUSSIAN_TRUSTED_CA)
        _ssl_context['ctx'] = ctx
    return _ssl_context['ctx']


# paymentWay из getOrderStatusExtended -> способ оплаты для отчётов.
PAYMENT_WAYS = {
    'SBP_C2B': 'СБП', 'SBP_C2B_BINDING': 'СБП', 'CARD': 'Карта', 'CARD_BINDING': 'Карта',
    'CARD_MOTO': 'Карта', 'ALFAPAY': 'AlfaPay', 'ALFAPAY_BINDING': 'AlfaPay', 'ALFA_ALFACLICK': 'Альфа-Клик',
    'APPLE_PAY': 'Apple Pay', 'APPLE_PAY_BINDING': 'Apple Pay', 'GOOGLE_PAY_CARD': 'Google Pay',
    'GOOGLE_PAY_CARD_BINDING': 'Google Pay', 'GOOGLE_PAY_TOKENIZED_BINDING': 'Google Pay',
    'YANDEX_PAY_CARD': 'Яндекс Pay', 'YANDEX_PAY_CARD_BINDING': 'Яндекс Pay', 'MIR_PAY': 'Мир Pay',
    'MIR_PAY_BINDING': 'Мир Pay', 'SAMSUNG_PAY': 'Samsung Pay',
}


def payment_way(order: Optional[Dict[str, Any]], params: Dict[str, Any]) -> Optional[str]:
    '''Способ оплаты: СБП / карта / кошельки. Статический QR СБП узнаём по templateId в уведомлении.'''
    way = str((order or {}).get('paymentWay') or ((order or {}).get('cardAuthInfo') or {}).get('paymentWay') or '').upper()
    if way:
        return PAYMENT_WAYS.get(way, way)
    if params.get('templateId') or (order or {}).get('sbpC2bInfo'):
        return 'СБП'
    return None


def _int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _rub(kopecks: Any) -> float:
    try:
        return round(float(kopecks or 0) / 100, 2)
    except (TypeError, ValueError):
        return 0.0


def checksum_string(params: Dict[str, Any]) -> str:
    pairs = sorted((k, v) for k, v in params.items() if k not in ('checksum', 'sign_alias'))
    return ''.join(f'{k};{v};' for k, v in pairs)


def verify_checksum(params: Dict[str, Any], secret: str) -> bool:
    given = str(params.get('checksum') or '').upper()
    if not given:
        return False
    calc = hmac.new(secret.encode('utf-8'), checksum_string(params).encode('utf-8'),
                    hashlib.sha256).hexdigest().upper()
    return hmac.compare_digest(calc, given)


def api_base(config: Dict[str, Any]) -> str:
    custom = (config.get('api_url') or '').strip().rstrip('/')
    if custom:
        return custom
    return API_URLS.get(config.get('environment') or 'prod', API_URLS['prod'])


def get_order_status(config: Dict[str, Any], md_order: Optional[str], order_number: Optional[str],
                     timeout: float = 10) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    '''getOrderStatusExtended.do: статус заказа и корзина (orderBundle).'''
    form: Dict[str, str] = {'language': 'ru'}
    if config.get('token'):
        form['token'] = config['token']
    else:
        form['userName'] = config.get('user_name') or ''
        form['password'] = config.get('password') or ''
    if md_order:
        form['orderId'] = md_order
    elif order_number:
        form['orderNumber'] = order_number
    else:
        return None, 'В уведомлении нет номера заказа'
    req = urllib.request.Request(
        f'{api_base(config)}/getOrderStatusExtended.do',
        data=urllib.parse.urlencode(form).encode('utf-8'),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return None, f'Альфа-Банк ответил ошибкой {e.code}'
    except Exception as e:
        return None, f'Не удалось связаться с Альфа-Банком: {str(e)[:150]}'
    error_code = str(data.get('errorCode') if data.get('errorCode') is not None else '0')
    if error_code not in ('0', ''):
        return None, f"Альфа-Банк: {data.get('errorMessage') or 'ошибка ' + error_code}"
    return data, None


def _attributes(item: Dict[str, Any]) -> Dict[str, Any]:
    block = item.get('itemAttributes') or {}
    attrs = (block.get('attributes') or block.get('itemAttributes') or []) if isinstance(block, dict) else []
    result = {}
    for a in attrs if isinstance(attrs, list) else []:
        if isinstance(a, dict) and a.get('name'):
            result[a['name']] = a.get('value')
    return result


def convert_items(bundle: Dict[str, Any]) -> List[Dict[str, Any]]:
    '''Позиции orderBundle.cartItems.items -> наш формат корзины (как у Т-Банка, суммы в рублях).'''
    cart = (bundle or {}).get('cartItems') or {}
    raw = cart.get('items') or []
    items = []
    for it in raw if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        q = it.get('quantity')
        quantity = float((q.get('value') if isinstance(q, dict) else q) or 0)
        measure = q.get('measure') if isinstance(q, dict) else it.get('measure')
        amount = _rub(it.get('depositedItemAmount') or it.get('itemAmount'))
        price_raw = it.get('itemPrice') if it.get('itemPrice') is not None else it.get('price')
        price = _rub(price_raw) if price_raw is not None else (round(amount / quantity, 2) if quantity else amount)
        tax = it.get('tax') if isinstance(it.get('tax'), dict) else {'taxType': it.get('taxType')}
        attrs = _attributes(it)
        item = {
            'name': str(it.get('name') if it.get('name') is not None else 'Товар'),
            'price': price,
            'quantity': quantity,
            'amount': amount,
            'tax': TAX_TYPES.get(_int(tax.get('taxType')), 'none') if tax.get('taxType') is not None else None,
            'payment_method': PAYMENT_METHODS.get(_int(attrs.get('paymentMethod'))),
            'payment_object': PAYMENT_OBJECTS.get(_int(attrs.get('paymentObject'))),
            'measurement_unit': measure if measure and not str(measure).isdigit() else None,
            'item_code': it.get('itemCode'),
            'position_id': it.get('positionId'),
        }
        if attrs.get('nomenclature'):
            item['mark_code'] = attrs.get('nomenclature')
        items.append(item)
    return items


def save_cart(cur, integration_id: int, company_id: int, md_order: str, order: Dict[str, Any]) -> int:
    bundle = order.get('orderBundle') or {}
    items = convert_items(bundle)
    customer = bundle.get('customerDetails') or {}
    receipt = {
        'Email': customer.get('email'), 'Phone': customer.get('phone'),
        'Customer': customer.get('fullName') or customer.get('contact'), 'CustomerInn': customer.get('inn'),
        'Taxation': None, 'orderBundle': bundle,
    }
    total = round(sum(i['amount'] for i in items), 2)
    cur.execute(f'''
        INSERT INTO {SCHEMA}.payment_carts
            (company_id, integration_id, payment_id, order_id, source, items, receipt, items_total, fiscal_data,
             fiscalized, receipt_id)
        VALUES (%s, %s, %s, %s, 'alfabank_order', %s, %s, %s, '{{}}'::jsonb, false, NULL)
        ON CONFLICT (integration_id, payment_id) DO UPDATE SET
            items = EXCLUDED.items, receipt = EXCLUDED.receipt, items_total = EXCLUDED.items_total,
            order_id = COALESCE(EXCLUDED.order_id, payment_carts.order_id), updated_at = NOW()
    ''', (company_id, integration_id, md_order, order.get('orderNumber'),
          json.dumps(items, ensure_ascii=False), json.dumps(receipt, ensure_ascii=False), total))
    return len(items)


def process(cur, integration_id: int, company_id: int, config: Dict[str, Any],
            webhook_settings: Dict[str, Any], params: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[str]]:
    '''
    Уведомление Альфа-Банка: проверка контрольной суммы (если задан ключ), статус по operation/status,
    запрос заказа с корзиной (getOrderStatusExtended), сохранение платежа и корзины.
    Returns: (подпись_верна, webhook_payment_id, ошибка)
    '''
    secret = (config.get('callback_secret') or '').strip()
    if secret and not verify_checksum(params, secret):
        return False, None, 'Неверная контрольная сумма уведомления'

    md_order = str(params.get('mdOrder') or '').strip()
    order_number = str(params.get('orderNumber') or '').strip() or None
    operation = str(params.get('operation') or '').strip().lower()
    status_flag = str(params.get('status') or '').strip()
    if not md_order:
        return True, None, 'В уведомлении нет mdOrder'

    status = OPERATION_STATUS.get((operation, status_flag))
    if not status:
        return True, None, None
    notify_key = NOTIFY_KEYS.get(status)
    if notify_key and not webhook_settings.get(notify_key, True):
        return True, None, None

    order, order_error = get_order_status(config, md_order, order_number)
    if order is None and not secret:
        # Без контрольной суммы подлинность подтверждает только ответ банка.
        return True, None, order_error or 'Не удалось подтвердить заказ в Альфа-Банке'

    amount = _rub((order or {}).get('amount') or params.get('amount'))
    if order:
        info = order.get('paymentAmountInfo') or {}
        if status == 'CONFIRMED' and info.get('depositedAmount'):
            amount = _rub(info['depositedAmount'])
        if status == 'REFUNDED' and info.get('refundedAmount'):
            amount = _rub(info['refundedAmount'])
        # Без ключа доверяем статусу банка, а не уведомлению.
        if not secret and status in ('AUTHORIZED', 'CONFIRMED') and order.get('orderStatus') not in (1, 2, '1', '2'):
            return True, None, f"Альфа-Банк не подтвердил оплату (статус заказа {order.get('orderStatus')})"
        save_cart(cur, integration_id, company_id, md_order, order)

    card = (order or {}).get('cardAuthInfo') or {}
    customer = ((order or {}).get('orderBundle') or {}).get('customerDetails') or {}
    raw = {'callback': params, 'order': order, 'order_error': order_error}
    cur.execute(f'''
        INSERT INTO {SCHEMA}.webhook_payments (
            integration_id, company_id, payment_id, terminal_key, amount, order_id, status, payment_status,
            error_code, customer_email, customer_phone, pan, card_type, exp_date, raw_data, payment_provider, origin
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'automation')
        ON CONFLICT (integration_id, payment_id, status) DO NOTHING
        RETURNING id
    ''', (
        integration_id, company_id, md_order, (order or {}).get('terminalId'), amount,
        order_number or (order or {}).get('orderNumber'), status, operation,
        str((order or {}).get('actionCode') if order and order.get('actionCode') is not None else '')[:10] or None,
        customer.get('email'), customer.get('phone'),
        card.get('maskedPan') or card.get('pan'), card.get('paymentSystem'),
        card.get('expiration'), json.dumps(raw, ensure_ascii=False), payment_way(order, params)
    ))
    row = cur.fetchone()
    # Корзину не получили - платёж всё равно принят: автоматизация дозапросит её у банка сама.
    return True, (row[0] if row else None), None

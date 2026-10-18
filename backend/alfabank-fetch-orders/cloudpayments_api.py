'''
CloudPayments (https://developers.cloudpayments.ru/#uvedomleniya).

Уведомления Pay / Confirm / Fail / Refund / Cancel приходят POST (form-urlencoded) или GET.
Тип уведомления в теле не передаётся - берём из ?type= в ссылке, иначе определяем по полям:
  PaymentTransactionId - Refund; Reason/ReasonCode без Status - Fail; Status - Pay/Confirm; иначе Cancel.
Подлинность: заголовки Content-HMAC / X-Content-HMAC = base64(HMAC-SHA256(API Secret, тело)).
Оплату (Pay/Confirm) всегда сверяем с API (POST /payments/get): так уведомление Check,
ошибочно направленное на наш адрес, не превратится в оплаченный платёж.
Ответ CloudPayments ждёт JSON {"code": 0}.
Состав чека - из Data.cloudpayments.CustomerReceipt.Items (если сайт передаёт чек в платёж),
иначе сценарий пробьёт одну позицию на сумму с назначением платежа.
'''
import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = 't_p83864310_fintech_payment_reco'
API_BASE = 'https://api.cloudpayments.ru'

NOTIFY_KEYS = {
    'AUTHORIZED': 'notify_on_authorized',
    'CONFIRMED': 'notify_on_confirmed',
    'REJECTED': 'notify_on_rejected',
    'CANCELED': 'notify_on_canceled',
    'REFUNDED': 'notify_on_refunded',
}

KINDS = ('pay', 'confirm', 'fail', 'refund', 'cancel')

# Ставка НДС CloudKassir (число) -> ставка кассы (АТОЛ).
VATS = {
    '0': 'vat0', '10': 'vat10', '20': 'vat20', '110': 'vat110', '120': 'vat120',
    '5': 'vat5', '7': 'vat7', '105': 'vat105', '107': 'vat107', '22': 'vat22', '122': 'vat122',
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

PAYMENT_METHOD_NAMES = {
    'sbp': 'СБП', 'tinkoffpay': 'T-Pay', 't-pay': 'T-Pay', 'tpay': 'T-Pay', 'sberpay': 'SberPay',
    'mirpay': 'Mir Pay', 'applepay': 'Apple Pay', 'googlepay': 'Google Pay', 'yandexpay': 'Яндекс Pay',
    'dolyame': 'Долями', 'installment': 'Рассрочка',
}


def _header(headers: Dict[str, Any], name: str) -> str:
    for k, v in (headers or {}).items():
        if str(k).lower() == name.lower():
            return str(v or '').strip()
    return ''


def verify_hmac(raw_body: str, headers: Dict[str, Any], secret: str) -> bool:
    '''HMAC-SHA256 тела (UTF-8) ключом API Secret, base64. Content-HMAC - по encoded, X-Content-HMAC - по decoded.'''
    if not secret or not raw_body:
        return False
    given = [h for h in (_header(headers, 'Content-HMAC'), _header(headers, 'X-Content-HMAC')) if h]
    if not given:
        return False
    variants = {raw_body, urllib.parse.unquote_plus(raw_body)}
    for body in variants:
        calc = base64.b64encode(hmac.new(secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).digest()).decode('ascii')
        if any(hmac.compare_digest(calc, g) for g in given):
            return True
    return False


def api_post(config: Dict[str, Any], path: str, payload: Dict[str, Any],
             timeout: float = 8) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
    '''POST к API CloudPayments (Basic: Public ID + API Secret). Returns: (ответ, ошибка, HTTP-код; 0 - нет связи).'''
    creds = f"{str(config.get('public_id') or '').strip()}:{str(config.get('api_secret') or '').strip()}"
    req = urllib.request.Request(
        f'{API_BASE}{path}', data=json.dumps(payload).encode('utf-8'), method='POST',
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Basic ' + base64.b64encode(creds.encode('utf-8')).decode('ascii')})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8') or '{}'), None, resp.status
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None, 'CloudPayments: неверные Public ID или API Secret', 401
        return None, f'CloudPayments ответил ошибкой {e.code}', e.code
    except Exception as e:
        return None, f'Не удалось связаться с CloudPayments: {str(e)[:120]}', 0


def is_retryable(error: Optional[str]) -> bool:
    e = error or ''
    return e.startswith('Не удалось связаться с CloudPayments') or e.startswith('CloudPayments ответил ошибкой 5')


def detect_kind(data: Dict[str, Any], params: Dict[str, Any]) -> str:
    explicit = str(params.get('type') or '').strip().lower()
    if explicit in KINDS:
        return explicit
    if data.get('PaymentTransactionId'):
        return 'refund'
    if (data.get('ReasonCode') not in (None, '') or data.get('Reason')) and not data.get('Status'):
        return 'fail'
    if data.get('Status'):
        return 'pay'
    return 'cancel'


def _json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith('{'):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _ci(obj: Dict[str, Any], *names: str) -> Any:
    '''Значение по ключу без учёта регистра (CustomerReceipt / customerReceipt).'''
    lower = {str(k).lower(): v for k, v in (obj or {}).items()}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def customer_receipt(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = _json(_ci(data, 'Data', 'JsonData'))
    cp = _json(_ci(payload, 'cloudpayments')) or payload
    receipt = _json(_ci(cp, 'CustomerReceipt', 'receipt'))
    return receipt


def _rub(value: Any) -> float:
    try:
        return round(float(str(value).replace(',', '.')), 2)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def convert_items(receipt: Dict[str, Any]) -> List[Dict[str, Any]]:
    '''Позиции CustomerReceipt.Items -> наш формат корзины (суммы в рублях).'''
    items = []
    for it in _ci(receipt, 'Items') or []:
        if not isinstance(it, dict):
            continue
        quantity = float(_rub(_ci(it, 'quantity')) or 0)
        price = _rub(_ci(it, 'price'))
        amount = _rub(_ci(it, 'amount')) or round(price * quantity, 2)
        vat_raw = _ci(it, 'vat')
        item = {
            'name': str(_ci(it, 'label') or 'Товар')[:128],
            'price': price,
            'quantity': quantity,
            'amount': amount,
            'tax': VATS.get(str(_int(vat_raw))) if vat_raw not in (None, '') else 'none',
            'payment_method': PAYMENT_METHODS.get(_int(_ci(it, 'method'))),
            'payment_object': PAYMENT_OBJECTS.get(_int(_ci(it, 'object'))),
            'measurement_unit': _ci(it, 'measurementUnit'),
            'excise': _ci(it, 'excise'),
            'country_code': _ci(it, 'countryOriginCode'),
            'declaration_number': _ci(it, 'customsDeclarationNumber'),
        }
        items.append({k: v for k, v in item.items() if v not in (None, '')})
    return items


def save_cart(cur, integration_id: int, company_id: int, payment_id: str, data: Dict[str, Any]) -> int:
    receipt = customer_receipt(data)
    items = convert_items(receipt)
    cart_receipt = {
        'Email': _ci(receipt, 'email') or data.get('Email'),
        'Phone': _ci(receipt, 'phone'),
        'Customer': _ci(receipt, 'customerInfo'),
        'CustomerInn': _ci(receipt, 'customerInn'),
        'Taxation': None,
        'description': data.get('Description'),
    }
    total = round(sum(float(i.get('amount') or 0) for i in items), 2)
    cur.execute(f'''
        INSERT INTO {SCHEMA}.payment_carts
            (company_id, integration_id, payment_id, order_id, source, items, receipt, items_total, fiscal_data,
             fiscalized, receipt_id)
        VALUES (%s, %s, %s, %s, 'cloudpayments_data', %s, %s, %s, '{{}}'::jsonb, false, NULL)
        ON CONFLICT (integration_id, payment_id) DO UPDATE SET
            items = EXCLUDED.items, receipt = EXCLUDED.receipt, items_total = EXCLUDED.items_total,
            order_id = COALESCE(EXCLUDED.order_id, payment_carts.order_id), updated_at = NOW()
    ''', (company_id, integration_id, payment_id, (str(data.get('InvoiceId'))[:255] if data.get('InvoiceId') else None),
          json.dumps(items, ensure_ascii=False), json.dumps(cart_receipt, ensure_ascii=False), total))
    return len(items)


def payment_method_name(data: Dict[str, Any]) -> Optional[str]:
    method = str(data.get('PaymentMethod') or '').strip()
    if method:
        return PAYMENT_METHOD_NAMES.get(method.lower().replace(' ', ''), method)[:100]
    return 'Карта' if data.get('CardLastFour') else None


def process(cur, integration_id: int, company_id: int, config: Dict[str, Any], webhook_settings: Dict[str, Any],
            data: Dict[str, Any], raw_body: str, headers: Dict[str, Any],
            params: Dict[str, Any]) -> Tuple[bool, Optional[int], Optional[str], Optional[str]]:
    '''
    Уведомление CloudPayments -> платёж. Returns: (подлинное, webhook_payment_id, ошибка, пометка «пропущено»)
    '''
    tx = str(data.get('TransactionId') or '').strip()
    if not tx:
        return True, None, 'Это не уведомление CloudPayments (нет TransactionId)', None
    kind = detect_kind(data, params)
    hmac_ok = verify_hmac(raw_body, headers, str(config.get('api_secret') or '').strip())

    api_model: Dict[str, Any] = {}
    if kind in ('pay', 'confirm') or not hmac_ok:
        resp, err, _ = api_post(config, '/payments/get', {'TransactionId': _int(tx) or tx})
        if resp is None:
            return True, None, err, None
        if not resp.get('Success') or not isinstance(resp.get('Model'), dict):
            if hmac_ok:
                api_model = {}
            else:
                return False, None, (f'CloudPayments не знает транзакцию {tx} на этом сайте '
                                     f'({resp.get("Message") or "не найдена"}) - уведомление отклонено'), None
        else:
            api_model = resp['Model']

    if kind == 'pay' or kind == 'confirm':
        api_status = str(api_model.get('Status') or '')
        if api_status == 'Completed':
            status = 'CONFIRMED'
        elif api_status == 'Authorized':
            status = 'AUTHORIZED'
        elif api_status in ('Refunded', 'Cancelled'):
            status = 'CONFIRMED'
        else:
            return True, None, None, f'Транзакция {tx} ещё не оплачена (статус в CloudPayments «{api_status or "—"}»)'
        amount = _rub(api_model.get('Amount') if api_model.get('Amount') is not None else data.get('Amount'))
        payment_id = tx
    elif kind == 'refund':
        status, amount = 'REFUNDED', _rub(data.get('Amount'))
        payment_id = str(data.get('PaymentTransactionId') or tx)
    elif kind == 'cancel':
        status, amount, payment_id = 'CANCELED', _rub(data.get('Amount')), tx
    else:
        status, amount, payment_id = 'REJECTED', _rub(data.get('Amount')), tx

    notify_key = NOTIFY_KEYS.get(status)
    if notify_key and not webhook_settings.get(notify_key, True):
        return True, None, None, 'Статус выключен в настройках уведомлений интеграции'

    merged = {**{k: v for k, v in api_model.items() if v not in (None, '')}, **data} if api_model else data
    if status in ('CONFIRMED', 'AUTHORIZED'):
        save_cart(cur, integration_id, company_id, payment_id, merged)

    receipt = customer_receipt(merged)
    pan = f"{merged.get('CardFirstSix') or ''}******{merged.get('CardLastFour')}" if merged.get('CardLastFour') else None
    raw = {'notification': data, 'kind': kind, 'hmac_valid': hmac_ok, 'transaction': api_model or None}
    cur.execute(f'''
        INSERT INTO {SCHEMA}.webhook_payments (
            integration_id, company_id, payment_id, terminal_key, amount, order_id, status, payment_status,
            error_code, customer_email, customer_phone, pan, card_type, exp_date, raw_data, payment_provider, origin
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'webhook')
        ON CONFLICT (integration_id, payment_id, status) DO NOTHING
        RETURNING id
    ''', (
        integration_id, company_id, payment_id, str(config.get('public_id') or '')[:100] or None, amount,
        (str(merged.get('InvoiceId'))[:100] if merged.get('InvoiceId') else None), status,
        str(merged.get('Status') or kind)[:50],
        (str(merged.get('ReasonCode'))[:10] if status == 'REJECTED' and merged.get('ReasonCode') not in (None, '') else None),
        (str(merged.get('Email') or _ci(receipt, 'email') or '')[:255] or None),
        (str(_ci(receipt, 'phone') or '')[:50] or None),
        pan, (str(merged.get('CardType'))[:20] if merged.get('CardType') else None),
        (str(merged.get('CardExpDate'))[:10] if merged.get('CardExpDate') else None),
        json.dumps(raw, ensure_ascii=False), payment_method_name(merged),
    ))
    row = cur.fetchone()
    return True, (row[0] if row else None), None, None

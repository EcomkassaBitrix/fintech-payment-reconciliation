import hashlib
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from ru_trusted_ca import build_ssl_context

SCHEMA = 't_p83864310_fintech_payment_reco'
API = 'https://securepay.tinkoff.ru/v2'
SELF_URL = 'https://functions.poehali.dev/51f17dfc-af76-4415-a5cc-329b1ddaaa8c'
SITE_URL = 'https://s-verka.ru'
SSL_CONTEXT = build_ssl_context()


def load_terminal(cur, only_enabled: bool = True) -> Optional[Dict[str, Any]]:
    '''
    Терминал Т‑Банка платформы. only_enabled - только если включён «Принимать оплату» (новые оплаты клиентов).
    Уведомления, статусы, возвраты и тест из админки работают с подключённым терминалом и при выключенном приёме.
    '''
    cur.execute(f'''
        SELECT terminal_key, terminal_password, is_test, config FROM {SCHEMA}.platform_payment_providers
        WHERE slug = 'tbank' AND terminal_key IS NOT NULL AND terminal_password IS NOT NULL
          AND (is_enabled = true OR %s = false)
    ''', (only_enabled,))
    r = cur.fetchone()
    if not r:
        return None
    return {'terminal_key': r[0], 'password': r[1], 'is_test': r[2], 'config': r[3] or {}}


def make_token(payload: Dict[str, Any], password: str) -> str:
    '''Подпись запроса: корневые скалярные поля + Password, по ключу, значения подряд, SHA-256.'''
    values = {}
    for k, v in payload.items():
        if k == 'Token' or isinstance(v, (dict, list)):
            continue
        values[k] = ('true' if v else 'false') if isinstance(v, bool) else str(v)
    values['Password'] = password
    return hashlib.sha256(''.join(values[k] for k in sorted(values)).encode('utf-8')).hexdigest()


def verify(data: Dict[str, Any], password: str) -> bool:
    return bool(data.get('Token')) and make_token(data, password) == data.get('Token')


def call(terminal: Dict[str, Any], method: str, payload: Dict[str, Any], timeout: float = 10) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    body = {'TerminalKey': terminal['terminal_key'], **payload}
    body['Token'] = make_token(body, terminal['password'])
    req = urllib.request.Request(f'{API}/{method}', data=json.dumps(body, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return None, f'Т‑Банк ответил ошибкой {e.code}'
    except Exception as e:
        return None, f'Нет связи с Т‑Банком: {str(e)[:120]}'
    print(f"[tbank-billing] {method} -> Success={data.get('Success')} Status={data.get('Status')} "
          f"ErrorCode={data.get('ErrorCode')} {data.get('Message') or ''} {data.get('Details') or ''}")
    if not data.get('Success'):
        msg = ' '.join(str(x) for x in (data.get('Message'), data.get('Details')) if x) or 'отказ без описания'
        return data, f"Т‑Банк: {msg} (код {data.get('ErrorCode')})"
    return data, None


def receipt(terminal: Dict[str, Any], title: str, amount_kop: int, phone: Optional[str], email: Optional[str]) -> Optional[Dict[str, Any]]:
    '''
    Чек для онлайн-кассы Т‑Банка: одна позиция - тариф подписки. Признаки способа (1214) и предмета
    (1212) расчёта, НДС, СНО и версия ФФД - из настроек терминала в админке. Для ФФД 1.2 обязательна
    единица измерения (2108). Контакт покупателя - почта, иначе телефон.
    '''
    cfg = terminal['config']
    if not cfg.get('receipt_enabled'):
        return None
    item: Dict[str, Any] = {
        'Name': title[:128], 'Price': amount_kop, 'Quantity': 1, 'Amount': amount_kop,
        'Tax': cfg.get('vat') or 'none',
        'PaymentMethod': cfg.get('payment_method') or 'full_payment',
        'PaymentObject': cfg.get('payment_object') or 'service',
    }
    if (cfg.get('ffd') or '1.2') == '1.2':
        item['MeasurementUnit'] = cfg.get('measurement_unit') or 'шт'
    r: Dict[str, Any] = {'Taxation': cfg.get('taxation') or 'usn_income', 'Items': [item]}
    if (cfg.get('ffd') or '1.2') == '1.2':
        r['FfdVersion'] = '1.2'
    if email:
        r['Email'] = email
    elif phone:
        digits = ''.join(ch for ch in phone if ch.isdigit())
        if digits:
            r['Phone'] = '+' + digits
    return r


def init_payment(terminal: Dict[str, Any], *, order_id: str, amount_kop: int, description: str, customer_key: str,
                 recurrent_first: bool, phone: Optional[str] = None, email: Optional[str] = None,
                 success_url: Optional[str] = None, fail_url: Optional[str] = None,
                 receipt_title: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    '''
    Init. Первый платёж - с Recurrent=Y и CustomerKey: Т‑Банк сохранит карту и пришлёт RebillId
    в уведомлении. Для автосписания - Init без формы оплаты, затем Charge с RebillId.
    '''
    payload: Dict[str, Any] = {
        'Amount': amount_kop, 'OrderId': order_id, 'Description': description[:140],
        'CustomerKey': customer_key, 'NotificationURL': f'{SELF_URL}?tbank_notify=1',
    }
    if recurrent_first:
        payload['Recurrent'] = 'Y'
        payload['OperationInitiatorType'] = '1'
        if success_url:
            payload['SuccessURL'] = success_url
        if fail_url:
            payload['FailURL'] = fail_url
    else:
        payload['OperationInitiatorType'] = 'R'
    rec = receipt(terminal, receipt_title or description, amount_kop, phone, email)
    if rec:
        payload['Receipt'] = rec
    return call(terminal, 'Init', payload)


def charge(terminal: Dict[str, Any], payment_id: str, rebill_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    return call(terminal, 'Charge', {'PaymentId': payment_id, 'RebillId': rebill_id}, timeout=12)


def get_state(terminal: Dict[str, Any], payment_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    return call(terminal, 'GetState', {'PaymentId': payment_id}, timeout=8)

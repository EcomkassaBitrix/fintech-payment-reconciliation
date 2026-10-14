import hashlib
import re
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from ru_trusted_ca import build_ssl_context

SCHEMA = 't_p83864310_fintech_payment_reco'
API = 'https://securepay.tinkoff.ru/v2'
SSL_CONTEXT = build_ssl_context()
TAXATIONS = ('osn', 'usn_income', 'usn_income_outcome', 'esn', 'patent')
VATS = ('none', 'vat0', 'vat5', 'vat7', 'vat10', 'vat20', 'vat22', 'vat105', 'vat107', 'vat110', 'vat120', 'vat122')
PAYMENT_METHODS = ('full_payment', 'full_prepayment', 'prepayment', 'advance', 'partial_payment', 'credit', 'credit_payment')
PAYMENT_OBJECTS = ('service', 'commodity', 'job', 'intellectual_activity', 'payment', 'agent_commission', 'composite', 'another')


def _probe(terminal_key: str, password: str) -> Tuple[bool, Optional[str]]:
    '''
    GetState по несуществующему платежу: 501 - нет такого терминала, 204 - неверный пароль,
    любой другой ответ - пара терминал + пароль верна.
    '''
    payload = {'TerminalKey': terminal_key, 'PaymentId': '7000000000'}
    values = {**payload, 'Password': password}
    payload['Token'] = hashlib.sha256(''.join(str(values[k]) for k in sorted(values)).encode('utf-8')).hexdigest()
    req = urllib.request.Request(f'{API}/GetState', data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return False, f'Т‑Банк ответил ошибкой {e.code}'
    except Exception as e:
        return False, f'Нет связи с Т‑Банком: {str(e)[:120]}'
    code = str(data.get('ErrorCode') or '0')
    if code == '501':
        return False, 'Т‑Банк не нашёл терминал с таким TerminalKey'
    if code == '204':
        return False, 'Неверный пароль терминала'
    return True, None


def save(cur, body: Dict[str, Any], user_id) -> Optional[str]:
    key = str(body.get('terminal_key') or '').strip()
    password = str(body.get('terminal_password') or '').strip()
    cur.execute(f"SELECT terminal_key, terminal_password FROM {SCHEMA}.platform_payment_providers WHERE slug = 'tbank'")
    row = cur.fetchone()
    if not row:
        return 'Провайдер Т‑Банк не найден'
    if not password and row[0] == key:
        password = row[1] or ''
    if not key or not password:
        return 'Укажите TerminalKey и пароль терминала'
    ok, err = _probe(key, password)
    if not ok:
        return err
    taxation = body.get('taxation') if body.get('taxation') in TAXATIONS else 'usn_income'
    vat = body.get('vat') if body.get('vat') in VATS else 'none'
    config = {
        'receipt_enabled': body.get('receipt_enabled') is not False, 'taxation': taxation, 'vat': vat,
        'payment_method': body.get('payment_method') if body.get('payment_method') in PAYMENT_METHODS else 'full_payment',
        'payment_object': body.get('payment_object') if body.get('payment_object') in PAYMENT_OBJECTS else 'service',
        'ffd': '1.05' if body.get('ffd') == '1.05' else '1.2',
        'measurement_unit': (str(body.get('measurement_unit') or 'шт').strip()[:16] or 'шт'),
        'receipt_email': (str(body.get('receipt_email') or '').strip()[:64] or None),
        'receipt_email_copy': bool(body.get('receipt_email_copy')),
    }
    if config['receipt_email'] and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', config['receipt_email']):
        return 'Проверьте почту для чеков'
    cur.execute(f'''
        UPDATE {SCHEMA}.platform_payment_providers SET terminal_key = %s, terminal_password = %s,
            is_test = %s, config = %s, connected_at = NOW(), connected_by = %s, updated_at = NOW()
        WHERE slug = 'tbank'
    ''', (key, password, key.upper().endswith('DEMO'), json.dumps(config), user_id))
    return None


def check(cur) -> Dict[str, Any]:
    cur.execute(f"SELECT terminal_key, terminal_password FROM {SCHEMA}.platform_payment_providers WHERE slug = 'tbank'")
    row = cur.fetchone()
    if not row or not row[0] or not row[1]:
        return {'success': False, 'error': 'Терминал не подключён'}
    ok, err = _probe(row[0], row[1])
    if not ok:
        return {'success': False, 'error': err}
    return {'success': True, 'shop': {'account_id': row[0], 'test': row[0].upper().endswith('DEMO'), 'status': 'терминал отвечает'}}

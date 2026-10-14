import hashlib
import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from ru_trusted_ca import build_ssl_context

SCHEMA = 't_p83864310_fintech_payment_reco'
TBANK_API = 'https://securepay.tinkoff.ru/v2'
SSL_CONTEXT = build_ssl_context()
PROVIDER_NAMES = {'tbank': 'Т‑Банк', 'yookassa': 'ЮKassa', 'manual': 'Без платёжной системы', 'platform': 'Начислено платформой'}
REFUNDABLE = ('tbank',)


def _token(payload: Dict[str, Any], password: str) -> str:
    values = {k: ('true' if v else 'false') if isinstance(v, bool) else str(v)
              for k, v in payload.items() if k != 'Token' and not isinstance(v, (dict, list))}
    values['Password'] = password
    return hashlib.sha256(''.join(values[k] for k in sorted(values)).encode('utf-8')).hexdigest()


def _tbank_cancel(cur, payment_id: str, amount_kop: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    cur.execute(f"SELECT terminal_key, terminal_password FROM {SCHEMA}.platform_payment_providers WHERE slug = 'tbank'")
    row = cur.fetchone()
    if not row or not row[0] or not row[1]:
        return None, 'Терминал Т‑Банка не подключён'
    body: Dict[str, Any] = {'TerminalKey': row[0], 'PaymentId': payment_id, 'Amount': amount_kop}
    body['Token'] = _token(body, row[1])
    req = urllib.request.Request(f'{TBANK_API}/Cancel', data=json.dumps(body).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return None, f'Т‑Банк ответил ошибкой {e.code}'
    except Exception as e:
        return None, f'Нет связи с Т‑Банком: {str(e)[:120]}'
    print(f"[refund] Cancel {payment_id} -> Success={data.get('Success')} Status={data.get('Status')} "
          f"ErrorCode={data.get('ErrorCode')} {data.get('Message') or ''} {data.get('Details') or ''}")
    if not data.get('Success'):
        msg = ' '.join(str(x) for x in (data.get('Message'), data.get('Details')) if x) or 'отказ без описания'
        return data, f"Т‑Банк: {msg} (код {data.get('ErrorCode')})"
    return data, None


def _row_json(r) -> Dict[str, Any]:
    provider = r[6] or r[7] or 'manual'
    return {
        'id': r[0], 'company_id': r[1], 'company_name': r[2], 'company_inn': r[3],
        'date': r[4], 'amount': float(r[5]), 'provider': provider,
        'provider_name': PROVIDER_NAMES.get(provider, provider),
        'status': r[8], 'error': r[9], 'tariff_name': r[10], 'period': r[11],
        'is_recurring': r[12], 'refunded_at': r[13],
        'refund_amount': float(r[14]) if r[14] is not None else None,
        'can_refund': r[8] == 'paid' and provider in REFUNDABLE and bool(r[15]),
    }


SELECT = f'''
    SELECT p.id, p.company_id, COALESCE(NULLIF(c.full_name, ''), c.name), c.inn,
           COALESCE(p.paid_at, p.created_at), p.amount, p.provider_slug, p.method, p.status, p.error_message,
           t.name, p.period, p.is_recurring, p.refunded_at, p.refund_amount, p.provider_payment_id
    FROM {SCHEMA}.subscription_payments p
    JOIN {SCHEMA}.companies c ON c.id = p.company_id
    JOIN {SCHEMA}.tariffs t ON t.id = p.tariff_id
'''


def list_transactions(cur, params: Dict[str, Any]) -> Dict[str, Any]:
    where, args = ['1=1'], []
    if params.get('provider'):
        where.append('COALESCE(p.provider_slug, p.method) = %s')
        args.append(params['provider'])
    if params.get('status'):
        where.append('p.status = %s')
        args.append(params['status'])
    if params.get('search'):
        where.append("(c.name ILIKE %s OR c.full_name ILIKE %s OR c.inn ILIKE %s)")
        q = f"%{params['search'].strip()}%"
        args += [q, q, q]
    limit = min(int(params.get('limit') or 50), 200)
    offset = max(int(params.get('offset') or 0), 0)
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.subscription_payments p JOIN {SCHEMA}.companies c ON c.id = p.company_id "
                f"WHERE {' AND '.join(where)}", tuple(args))
    total = cur.fetchone()[0]
    cur.execute(f"{SELECT} WHERE {' AND '.join(where)} ORDER BY COALESCE(p.paid_at, p.created_at) DESC, p.id DESC "
                f"LIMIT {limit} OFFSET {offset}", tuple(args))
    return {'success': True, 'total': total, 'transactions': [_row_json(r) for r in cur.fetchall()]}


def refund(cur, payment_id: int, user_id) -> Dict[str, Any]:
    '''Полный возврат платежа подписки через платёжную систему. Срок подписки не меняется.'''
    cur.execute(f'{SELECT} WHERE p.id = %s FOR UPDATE OF p', (payment_id,))
    r = cur.fetchone()
    if not r:
        return {'success': False, 'error': 'Платёж не найден'}
    tx = _row_json(r)
    if tx['status'] == 'refunded':
        return {'success': False, 'error': 'Платёж уже возвращён'}
    if not tx['can_refund']:
        return {'success': False, 'error': f"Возврат через «{tx['provider_name']}» не поддерживается — верните деньги вручную"}
    data, err = _tbank_cancel(cur, r[15], int(round(tx['amount'] * 100)))
    if err:
        return {'success': False, 'error': err}
    refunded = (data or {}).get('OriginalAmount', 0) - (data or {}).get('NewAmount', 0)
    amount = round(refunded / 100, 2) if refunded else tx['amount']
    cur.execute(f'''
        UPDATE {SCHEMA}.subscription_payments SET status = 'refunded', refunded_at = NOW(), refunded_by = %s,
            refund_amount = %s, updated_at = NOW() WHERE id = %s
    ''', (user_id, amount, payment_id))
    cur.execute(f'{SELECT} WHERE p.id = %s', (payment_id,))
    return {'success': True, 'transaction': _row_json(cur.fetchone())}

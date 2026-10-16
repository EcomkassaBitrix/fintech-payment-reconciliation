import hashlib
import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import alfabank_api
from ru_trusted_ca import build_ssl_context

SCHEMA = 't_p83864310_fintech_payment_reco'
TBANK_API = 'https://securepay.tinkoff.ru/v2'
_ssl: Dict[str, Any] = {}

# Итог проверки: paid - платёж оплачен в платёжной системе; not_paid - система ответила,
# что не оплачен/отменён; unknown - проверить нечем или все системы недоступны (повторим позже).
Verdict = Tuple[str, str, Dict[str, Any]]


def _ctx():
    if 'ctx' not in _ssl:
        _ssl['ctx'] = build_ssl_context()
    return _ssl['ctx']


def _config(raw: Any) -> Dict[str, Any]:
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _integrations(cur, company_id: int, slug: str) -> List[Tuple[int, str, Dict[str, Any]]]:
    cur.execute(f'''
        SELECT ui.id, ui.name, ui.config FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug = %s AND ui.status = 'active'
        ORDER BY ui.id
    ''', (company_id, slug))
    return [(r[0], r[1], _config(r[2])) for r in cur.fetchall()]


def _tbank_call(method: str, config: Dict[str, Any], params: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    terminal = str(config.get('terminal_id') or '').strip()
    password = str(config.get('terminal_password') or '').strip()
    if not terminal or not password:
        return None, 'в интеграции не указан Terminal ID или пароль'
    payload = {'TerminalKey': terminal, **params}
    values = {**payload, 'Password': password}
    payload['Token'] = hashlib.sha256(''.join(str(values[k]) for k in sorted(values)).encode('utf-8')).hexdigest()
    req = urllib.request.Request(f'{TBANK_API}/{method}', data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8, context=_ctx()) as resp:
            return json.loads(resp.read().decode('utf-8')), None
    except urllib.error.HTTPError as e:
        return None, f'Т-Банк ответил ошибкой {e.code}'
    except Exception as e:
        return None, f'нет связи с Т-Банком: {str(e)[:120]}'


def _tbank_by_order(config: Dict[str, Any], order_id: str) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    '''CheckOrder по номеру заказа (OrderId): (paid/not_paid/None - не найден, данные, ошибка связи).'''
    data, err = _tbank_call('CheckOrder', config, {'OrderId': order_id})
    if data is None:
        return None, {}, err
    payments = data.get('Payments') or []
    if not payments:
        return None, {}, None
    paid = [p for p in payments if str(p.get('Status')) == 'CONFIRMED']
    if paid:
        p = paid[0]
        return 'paid', {'payment_id': str(p.get('PaymentId') or ''), 'amount': round(float(p.get('Amount') or 0) / 100, 2),
                        'status': 'CONFIRMED'}, None
    return 'not_paid', {'statuses': [str(p.get('Status')) for p in payments]}, None


def _tbank_by_payment(config: Dict[str, Any], payment_id: str) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    data, err = _tbank_call('GetState', config, {'PaymentId': payment_id})
    if data is None:
        return None, {}, err
    if not data.get('Success') and not data.get('Status'):
        return None, {}, None
    status = str(data.get('Status') or '')
    info = {'payment_id': payment_id, 'amount': round(float(data.get('Amount') or 0) / 100, 2), 'status': status}
    return ('paid' if status == 'CONFIRMED' else 'not_paid'), info, None


def _alfa(config: Dict[str, Any], md_order: Optional[str], order_number: Optional[str]) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
    order, err = alfabank_api.get_order_status(config, md_order, order_number, timeout=8)
    if not order:
        if err and ('не найден' in err.lower() or 'not found' in err.lower()):
            return None, {}, None
        return None, {}, err
    status = order.get('orderStatus')
    info = {'status': str(status), 'amount': round(float(order.get('amount') or 0) / 100, 2)}
    return ('paid' if str(status) == '2' else 'not_paid'), info, None


ORDER_CHECKERS = {'tbank': ('Т-Банк', _tbank_by_order), 'alfabank': ('Альфа-Банк', lambda c, o: _alfa(c, None, o))}


def verify_order(cur, company_id: int, order_id: str) -> Verdict:
    '''
    Ищет оплату заказа (номер заказа = UUID счёта Екомкассы) во всех подключённых эквайрингах
    компании, где можно спросить статус по номеру заказа. Первый «оплачен» - платёж подтверждён.
    '''
    checked, errors, not_paid = [], [], []
    for slug, (label, checker) in ORDER_CHECKERS.items():
        for _, name, config in _integrations(cur, company_id, slug):
            verdict, info, err = checker(config, order_id)
            checked.append(f'{label} «{name}»')
            if err:
                errors.append(f'{label} «{name}»: {err}')
            elif verdict == 'paid':
                return 'paid', f'{label} «{name}»: заказ {order_id} оплачен', {**info, 'system': label}
            elif verdict == 'not_paid':
                not_paid.append(f"{label} «{name}» ({', '.join(info.get('statuses') or [info.get('status', '')])})")
    if not_paid:
        return 'not_paid', f"Заказ {order_id} не оплачен: {'; '.join(not_paid)}", {}
    if errors:
        return 'unknown', 'Не удалось проверить: ' + '; '.join(errors), {}
    if not checked:
        return 'unknown', 'Нет эквайринга, где можно проверить заказ по номеру (поддерживаются Т-Банк и Альфа-Банк)', {}
    return 'not_paid', f"Заказ {order_id} не найден: {', '.join(checked)}", {}


def verify_payment(cur, company_id: int, payment: Dict[str, Any]) -> Verdict:
    '''Проверка уже сохранённого платежа в той платёжной системе, откуда он пришёл.'''
    slug = payment.get('provider_slug')
    if slug == 'ecomkassa_gateway':
        return verify_order(cur, company_id, str(payment['payment_id']))
    if slug in ('tbank', 'alfabank'):
        cur.execute(f'SELECT config FROM {SCHEMA}.user_integrations WHERE id = %s', (payment['integration_id'],))
        row = cur.fetchone()
        config = _config(row[0] if row else None)
        if slug == 'tbank':
            verdict, info, err = _tbank_by_payment(config, str(payment['payment_id']))
            label = 'Т-Банк'
        else:
            verdict, info, err = _alfa(config, str(payment['payment_id']), payment.get('order_id'))
            label = 'Альфа-Банк'
        if err:
            return 'unknown', f'{label}: {err}', {}
        if verdict == 'paid':
            return 'paid', f"{label}: платёж #{payment['payment_id']} оплачен", {**info, 'system': label}
        if verdict == 'not_paid':
            return 'not_paid', f"{label}: платёж #{payment['payment_id']} в статусе {info.get('status')} - не оплачен", {}
        return 'not_paid', f"{label}: платёж #{payment['payment_id']} не найден", {}
    return 'unknown', 'Для этой платёжной системы проверка статуса пока недоступна', {}

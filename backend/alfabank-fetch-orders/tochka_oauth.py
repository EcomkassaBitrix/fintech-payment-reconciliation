'''
OAuth 2.0 Точки (https://developers.tochka.com/docs/tochka-api/algoritm-raboty-po-oauth-2.0).
Одинаковая копия лежит в tochka-oauth, tochka-accounts-list и bank-statement-sync.

Флоу: client_credentials-токен -> consent (список разрешений) -> ссылка подтверждения
-> code на redirect_uri -> access_token (24 ч) + refresh_token (30 дней).
Токены компании храним в company_bank_oauth_grants (provider_slug = 'tochka_account')
и обновляем по refresh_token за 10 минут до истечения.
'''
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from ru_trusted_ca import build_ssl_context

SCHEMA = 't_p83864310_fintech_payment_reco'
PROVIDER_SLUG = 'tochka_account'
TOKEN_URL = 'https://enter.tochka.com/connect/token'
AUTHORIZE_URL = 'https://enter.tochka.com/connect/authorize'
CONSENTS_URL = 'https://enter.tochka.com/uapi/v1.0/consents'
# Один и тот же набор scope во всех запросах флоу - требование Точки.
SCOPE = 'accounts balances customers statements acquiring'
PERMISSIONS = [
    'ReadAccountsBasic', 'ReadAccountsDetail', 'ReadBalances', 'ReadStatements',
    'ReadCustomerData', 'ReadAcquiringData', 'ManageWebhookData',
]
API_BASE = 'https://enter.tochka.com/uapi'
# Вебхук OAuth-приложения один на всех клиентов: в теле есть customerCode,
# по нему webhook-receive находит интеграцию эквайринга нужной компании.
WEBHOOK_URL = 'https://functions.poehali.dev/a923b457-57a6-4eb2-b566-9a9d65cb04e8?source=tochka'
WEBHOOK_EVENTS = ['acquiringInternetPayment']

_ssl = {}


def ssl_context():
    if 'ctx' not in _ssl:
        _ssl['ctx'] = build_ssl_context()
    return _ssl['ctx']


def is_configured() -> bool:
    return bool(os.environ.get('TOCHKA_CLIENT_ID')) and bool(os.environ.get('TOCHKA_CLIENT_SECRET'))


def _post(url: str, data: bytes, headers: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    req = urllib.request.Request(url, data=data, method='POST', headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10, context=ssl_context()) as resp:
            return json.loads(resp.read().decode('utf-8')), None
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace') if e.fp else ''
        print(f'[tochka-oauth] POST {url} -> HTTP {e.code}: {body[:500]}')
        return None, f'Точка ответила ошибкой {e.code}'
    except Exception as e:
        print(f'[tochka-oauth] POST {url} -> {e}')
        return None, f'Не удалось связаться с Точкой: {str(e)[:120]}'


def _token_request(fields: Dict[str, str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    form = {
        'client_id': os.environ.get('TOCHKA_CLIENT_ID', ''),
        'client_secret': os.environ.get('TOCHKA_CLIENT_SECRET', ''),
        **fields,
    }
    return _post(TOKEN_URL, urllib.parse.urlencode(form).encode('utf-8'),
                 {'Content-Type': 'application/x-www-form-urlencoded'})


def build_authorize_url(redirect_uri: str, state: str) -> Tuple[Optional[str], Optional[str]]:
    '''Шаги 2-4: токен приложения -> consent -> ссылка подтверждения для клиента.'''
    app_token, err = _token_request({'grant_type': 'client_credentials', 'scope': SCOPE})
    if not app_token or not app_token.get('access_token'):
        return None, err or 'Точка не выдала токен приложения'
    consent, err = _post(
        CONSENTS_URL,
        json.dumps({'Data': {'permissions': PERMISSIONS}}).encode('utf-8'),
        {'Content-Type': 'application/json', 'Authorization': f"Bearer {app_token['access_token']}"},
    )
    consent_id = ((consent or {}).get('Data') or {}).get('consentId')
    if not consent_id:
        return None, err or 'Точка не создала список разрешений'
    query = urllib.parse.urlencode({
        'client_id': os.environ.get('TOCHKA_CLIENT_ID', ''),
        'response_type': 'code',
        'state': state,
        'redirect_uri': redirect_uri,
        'scope': SCOPE,
        'consent_id': consent_id,
    }, quote_via=urllib.parse.quote)
    return f'{AUTHORIZE_URL}?{query}', None


def exchange_code(code: str, redirect_uri: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    '''Шаг 5: code (живёт 5 минут) -> access_token + refresh_token.'''
    data, err = _token_request({
        'grant_type': 'authorization_code', 'scope': SCOPE, 'code': code, 'redirect_uri': redirect_uri,
    })
    if not data or not data.get('access_token'):
        return None, err or 'Точка не выдала токен'
    return data, None


def save_grant(cur, company_id: int, token_data: Dict[str, Any]) -> None:
    cur.execute(f'''
        INSERT INTO {SCHEMA}.company_bank_oauth_grants
            (company_id, provider_slug, is_sandbox, access_token, refresh_token, scope, expires_at)
        VALUES (%s, %s, false, %s, %s, %s, NOW() + (%s || ' seconds')::interval)
        ON CONFLICT (company_id, provider_slug) DO UPDATE SET
            is_sandbox = false,
            access_token = EXCLUDED.access_token,
            refresh_token = COALESCE(EXCLUDED.refresh_token, company_bank_oauth_grants.refresh_token),
            scope = EXCLUDED.scope,
            expires_at = EXCLUDED.expires_at,
            revoked_at = NULL,
            updated_at = NOW()
    ''', (company_id, PROVIDER_SLUG, token_data['access_token'], token_data.get('refresh_token'),
          SCOPE, str(int(token_data.get('expires_in') or 86400))))


def get_access_token(cur, company_id: int) -> Tuple[Optional[str], Optional[str]]:
    '''
    Действующий access_token компании. Если истекает в ближайшие 10 минут - обновляем
    по refresh_token (Точка выдаёт новую пару, старый refresh_token больше не годится).
    '''
    cur.execute(f'''
        SELECT access_token, refresh_token, expires_at > NOW() + INTERVAL '10 minutes', revoked_at IS NOT NULL
        FROM {SCHEMA}.company_bank_oauth_grants
        WHERE company_id = %s AND provider_slug = %s
        FOR UPDATE
    ''', (company_id, PROVIDER_SLUG))
    row = cur.fetchone()
    if not row:
        return None, 'Точка не подключена через OAuth - нажмите «Подключить через Точку»'
    access_token, refresh_token, fresh, revoked = row
    if revoked:
        return None, EXPIRED_MESSAGE
    if fresh:
        return access_token, None
    if not refresh_token:
        mark_revoked(cur, company_id)
        return None, EXPIRED_MESSAGE
    data, err = _token_request({'grant_type': 'refresh_token', 'refresh_token': refresh_token})
    if not data or not data.get('access_token'):
        # Точка отвечает 400/401 на просроченный или отозванный refresh_token - дальше только переподключение.
        if err and ('400' in err or '401' in err):
            mark_revoked(cur, company_id)
            return None, EXPIRED_MESSAGE
        return None, f'Не удалось обновить доступ к Точке: {err}'
    save_grant(cur, company_id, data)
    cur.connection.commit()
    return data['access_token'], None


EXPIRED_MESSAGE = 'Доступ к Точке истёк - подключите счёт заново'


def mark_revoked(cur, company_id: int) -> None:
    cur.execute(f'''
        UPDATE {SCHEMA}.company_bank_oauth_grants SET revoked_at = NOW(), updated_at = NOW()
        WHERE company_id = %s AND provider_slug = %s AND revoked_at IS NULL
    ''', (company_id, PROVIDER_SLUG))
    cur.connection.commit()


def is_connected(cur, company_id: int) -> bool:
    '''Доступ рабочий: есть refresh_token, Точка его не отклоняла и он моложе 30 дней.'''
    cur.execute(f'''
        SELECT 1 FROM {SCHEMA}.company_bank_oauth_grants
        WHERE company_id = %s AND provider_slug = %s AND refresh_token IS NOT NULL
          AND revoked_at IS NULL AND updated_at > NOW() - INTERVAL '30 days'
    ''', (company_id, PROVIDER_SLUG))
    return cur.fetchone() is not None


def _api(method: str, path: str, token: str, body: Optional[Dict[str, Any]] = None
         ) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
    data = json.dumps(body).encode('utf-8') if body is not None else None
    headers = {'Authorization': f'Bearer {token}'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(f'{API_BASE}{path}', data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8, context=ssl_context()) as resp:
            raw = resp.read().decode('utf-8')
            return (json.loads(raw) if raw else {}), resp.status, None
    except urllib.error.HTTPError as e:
        text = e.read().decode('utf-8', 'replace') if e.fp else ''
        print(f'[tochka-oauth] {method} {path} -> HTTP {e.code}: {text[:500]}')
        return None, e.code, None
    except Exception as e:
        print(f'[tochka-oauth] {method} {path} -> {e}')
        return None, None, str(e)[:120]


def business_customers(token: str) -> List[Dict[str, Any]]:
    data, _, _ = _api('GET', '/open-banking/v1.0/customers', token)
    out = []
    for c in ((data or {}).get('Data') or {}).get('Customer', []):
        if c.get('customerType') == 'Business' and c.get('customerCode'):
            out.append({'customer_code': str(c['customerCode']),
                        'name': c.get('shortName') or c.get('fullName') or str(c['customerCode'])})
    return out


def retailers(token: str, customer_code: str) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    data, status, _ = _api('GET', f'/acquiring/v1.0/retailers?customerCode={customer_code}', token)
    items = ((data or {}).get('Data') or {}).get('Retailer') or []
    out = []
    for r in items if isinstance(items, list) else []:
        merchant = r.get('merchantId') or r.get('MerchantId')
        if merchant:
            out.append({'merchant_id': str(merchant), 'terminal_id': str(r.get('terminalId') or '') or None,
                        'name': r.get('name') or r.get('retailerName') or r.get('shortName')})
    return out, status


def ensure_webhook(token: str) -> Optional[str]:
    '''
    Подписка приложения на оплаты по платёжным ссылкам (Create/Edit Webhook). Повторный вызов безопасен.
    Вебхук принадлежит приложению (client_id), поэтому при отказе токену клиента пробуем токен приложения.
    '''
    err = _ensure_webhook(token)
    if err:
        app_token, _ = _token_request({'grant_type': 'client_credentials', 'scope': SCOPE})
        if app_token and app_token.get('access_token'):
            app_err = _ensure_webhook(app_token['access_token'])
            if not app_err:
                return None
    return err


def _ensure_webhook(token: str) -> Optional[str]:
    client_id = os.environ.get('TOCHKA_CLIENT_ID', '')
    data, status, err = _api('GET', f'/webhook/v1.0/{client_id}', token)
    current = (data or {}).get('Data') or {}
    events = current.get('webhooksList') or []
    if current.get('url') == WEBHOOK_URL and all(e in events for e in WEBHOOK_EVENTS):
        return None
    body = {'webhooksList': sorted(set(events) | set(WEBHOOK_EVENTS)), 'url': WEBHOOK_URL}
    method = 'POST' if current.get('url') else 'PUT'
    _, status, err = _api(method, f'/webhook/v1.0/{client_id}', token, body)
    if status == 200:
        return None
    if status == 403:
        return 'Точка не дала права на вебхуки - подключитесь через Точку заново'
    return err or f'Точка не создала вебхук (ошибка {status})'

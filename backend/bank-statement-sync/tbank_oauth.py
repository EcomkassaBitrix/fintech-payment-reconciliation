import json
import os
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional

from ru_trusted_ca import build_ssl_context

TBANK_SSL_CONTEXT = build_ssl_context()

API_BASE = 'https://business.tbank.ru/openapi/api/v1'
API_BASE_V4 = 'https://business.tbank.ru/openapi/api/v4'
OAUTH_AUTHORIZE_URL = 'https://id.tbank.ru/auth/authorize'
OAUTH_TOKEN_URL = 'https://id.tbank.ru/auth/token'


def is_production_configured() -> bool:
    '''Партнёрские ключи Т-Банка (T-Business ID) выданы платформе.'''
    return bool(os.environ.get('TBANK_CLIENT_ID')) and bool(os.environ.get('TBANK_CLIENT_SECRET'))


def build_authorize_url(redirect_uri: str, state: str) -> str:
    '''Ссылка партнёрской интеграции - открывает OAuth-согласие T-Business ID владельцу компании.'''
    client_id = os.environ.get('TBANK_CLIENT_ID', '')
    params = urllib.parse.urlencode({
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'accounts',
        'state': state
    })
    return f'{OAUTH_AUTHORIZE_URL}?{params}'


def exchange_code_for_token(code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
    '''Обмен authorization code на access/refresh токен. Работает только при выданных ключах банка.'''
    client_id = os.environ.get('TBANK_CLIENT_ID', '')
    client_secret = os.environ.get('TBANK_CLIENT_SECRET', '')

    data = urllib.parse.urlencode({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret
    }).encode('utf-8')

    req = urllib.request.Request(OAUTH_TOKEN_URL, data=data, method='POST',
                                  headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=10, context=TBANK_SSL_CONTEXT) as response:
            return json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def _as_datetime(value: str, end_of_day: bool) -> str:
    '''«2026-10-15» -> «2026-10-15T00:00:00Z» (или 23:59:59Z для конца периода); дата со временем - как есть.'''
    value = (value or '').strip()
    if len(value) == 10:
        return f"{value}T{'23:59:59' if end_of_day else '00:00:00'}Z"
    return value


def _request(path: str, access_token: str, base: str = API_BASE) -> Optional[Any]:
    if not access_token:
        return None
    req = urllib.request.Request(f'{base}{path}', headers={'Authorization': f'Bearer {access_token}'})
    try:
        with urllib.request.urlopen(req, timeout=15, context=TBANK_SSL_CONTEXT) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            details = e.read().decode('utf-8')[:300]
        except Exception:
            details = ''
        print(f'[tbank] {path.split("?")[0]} -> HTTP {e.code}: {details}')
        return None
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f'[tbank] {path.split("?")[0]} -> {type(e).__name__}: {e}')
        return None


def fetch_company_info(access_token: str) -> Optional[Dict[str, Any]]:
    '''Данные компании по токену Т-Бизнес. Успешный ответ = токен рабочий.'''
    return _request('/company', access_token)


def fetch_accounts(access_token: str) -> Optional[List[Dict[str, Any]]]:
    '''Список расчётных счетов компании, доступных по токену.'''
    return _request('/bank-accounts', access_token, API_BASE_V4) or _request('/bank-accounts', access_token)


def fetch_statement(access_token: str, account_number: str, date_from: str,
                     date_to: Optional[str] = None,
                     cursor: Optional[str] = None) -> Optional[Dict[str, Any]]:
    '''Выписка по счёту через T-API (https://developer.tbank.ru/docs/products/account-info).'''
    # T-API принимает только дату со временем (date-time): «2026-10-15» отклоняется с VALIDATION_ERROR.
    # Планировщик передаёт календарные дни - дополняем началом и концом дня.
    query = {'accountNumber': account_number, 'from': _as_datetime(date_from, end_of_day=False)}
    if date_to:
        query['to'] = _as_datetime(date_to, end_of_day=True)
    if cursor:
        query['cursor'] = cursor

    path = f'/statement?{urllib.parse.urlencode(query)}'
    return _request(path, access_token)
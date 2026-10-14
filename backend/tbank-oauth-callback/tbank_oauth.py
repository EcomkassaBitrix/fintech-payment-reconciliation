import json
import os
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional

from ru_trusted_ca import build_ssl_context

TBANK_SSL_CONTEXT = build_ssl_context()

# T-Business ID / T-API хосты. Песочница не требует реального OAuth-обмена -
# запросы принимаются с фиксированным тестовым токеном.
SANDBOX_TOKEN = 'TBankSandboxToken'
SANDBOX_API_BASE = 'https://business.tbank.ru/openapi/sandbox/api/v1'
PRODUCTION_API_BASE = 'https://business.tbank.ru/openapi/api/v1'
OAUTH_AUTHORIZE_URL = 'https://id.tbank.ru/auth/authorize'
OAUTH_TOKEN_URL = 'https://id.tbank.ru/auth/token'


def is_production_configured() -> bool:
    '''Партнёрские ключи Т-Банка ещё не выданы (заявка на T-ID подаётся при объёме от 30 000 авторизаций/мес).'''
    return bool(os.environ.get('TBANK_CLIENT_ID')) and bool(os.environ.get('TBANK_CLIENT_SECRET'))


def build_authorize_url(redirect_uri: str, state: str) -> str:
    '''Ссылка "Подключить через Т-Банк" - открывает OAuth-согласие T-Business ID владельцу компании.'''
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
    '''Боевой обмен authorization code на access/refresh токен. Работает только при выданных ключах банка.'''
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


def _request(path: str, access_token: str, is_sandbox: bool) -> Optional[Any]:
    base_url = SANDBOX_API_BASE if is_sandbox else PRODUCTION_API_BASE
    token = SANDBOX_TOKEN if is_sandbox else access_token
    req = urllib.request.Request(f'{base_url}{path}', headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=15, context=TBANK_SSL_CONTEXT) as response:
            return json.loads(response.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def fetch_company_info(access_token: str, is_sandbox: bool = True) -> Optional[Dict[str, Any]]:
    '''Данные компании, привязанной к OAuth-согласию T-Business ID.'''
    return _request('/company', access_token, is_sandbox)


def fetch_accounts(access_token: str, is_sandbox: bool = True) -> Optional[List[Dict[str, Any]]]:
    '''Список расчётных счетов компании, доступных по OAuth-согласию T-Business ID.'''
    return _request('/bank-accounts', access_token, is_sandbox)


def fetch_statement(access_token: str, account_number: str, date_from: str,
                     date_to: Optional[str] = None, is_sandbox: bool = True,
                     cursor: Optional[str] = None) -> Optional[Dict[str, Any]]:
    '''Получение выписки по счёту через T-API (https://developer.tbank.ru/docs/products/account-info).'''
    query = {'accountNumber': account_number, 'from': date_from}
    if date_to:
        query['to'] = date_to
    if cursor:
        query['cursor'] = cursor

    path = f'/statement?{urllib.parse.urlencode(query)}'
    return _request(path, access_token, is_sandbox)

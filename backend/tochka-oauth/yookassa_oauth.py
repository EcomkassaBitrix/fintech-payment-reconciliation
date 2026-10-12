import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

import psycopg2
from auth_guard import guard

SCHEMA = 't_p83864310_fintech_payment_reco'
PROVIDER_SLUG = 'yookassa'
AUTHORIZE_URL = 'https://yookassa.ru/oauth/v2/authorize'
TOKEN_URL = 'https://yookassa.ru/oauth/v2/token'
API_BASE = 'https://api.yookassa.ru/v3'


def _resp(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(payload, ensure_ascii=False, default=str),
        'isBase64Encoded': False
    }


def is_configured() -> bool:
    return bool(os.environ.get('YOOKASSA_CLIENT_ID')) and bool(os.environ.get('YOOKASSA_CLIENT_SECRET'))


def exchange_code(code: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    '''Код подтверждения (живёт 5 минут) -> OAuth-токен. Клиент и пароль - Basic-авторизацией.'''
    creds = f"{os.environ['YOOKASSA_CLIENT_ID']}:{os.environ['YOOKASSA_CLIENT_SECRET']}"
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode({'grant_type': 'authorization_code', 'code': code}).encode('utf-8'),
        method='POST',
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic ' + base64.b64encode(creds.encode('utf-8')).decode('ascii'),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace') if e.fp else ''
        print(f'[yookassa-oauth] token -> HTTP {e.code}: {body[:500]}')
        try:
            desc = json.loads(body).get('error_description') or json.loads(body).get('error')
        except Exception:
            desc = None
        return None, f'ЮKassa ответила ошибкой {e.code}' + (f': {desc}' if desc else '')
    except Exception as e:
        return None, f'Не удалось связаться с ЮKassa: {str(e)[:120]}'
    if not data.get('access_token'):
        return None, 'ЮKassa не выдала токен'
    return data, None


def shop_info(token: str) -> Tuple[Optional[Dict[str, Any]], Optional[int]]:
    '''Настройки магазина, к которому выдан доступ (GET /v3/me).'''
    req = urllib.request.Request(f'{API_BASE}/me', headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode('utf-8')), None
    except urllib.error.HTTPError as e:
        print(f'[yookassa-oauth] /me -> HTTP {e.code}')
        return None, e.code
    except Exception as e:
        print(f'[yookassa-oauth] /me -> {e}')
        return None, 0


def grant_row(cur, company_id: int):
    cur.execute(f'''
        SELECT access_token, scope, expires_at, created_at, updated_at FROM {SCHEMA}.company_bank_oauth_grants
        WHERE company_id = %s AND provider_slug = %s AND revoked_at IS NULL
          AND (expires_at IS NULL OR expires_at > NOW())
    ''', (company_id, PROVIDER_SLUG))
    return cur.fetchone()


def yookassa_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    '''
    Подключение магазина ЮKassa по OAuth (партнёрское API) от имени компании.
    GET  ?action=status&company_id=..        -> настроено ли приложение, подключён ли магазин
    GET  ?action=authorize_url&company_id=.. -> ссылка на выдачу прав в ЮKassa
    POST {code, company_id}                  -> обмен кода на токен, проверка магазина, сохранение
    POST {action: "disconnect", company_id}  -> отключить магазин (отозвать у себя)
    '''
    denied = guard(event)
    if denied:
        return denied

    method = event.get('httpMethod', 'GET')
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        if method == 'GET':
            params = event.get('queryStringParameters') or {}
            company_id = params.get('company_id')
            if not company_id:
                return _resp(400, {'error': 'company_id required'})
            action = params.get('action')

            if action == 'status':
                row = grant_row(cur, int(company_id))
                shop = None
                if row and params.get('check') == '1':
                    shop, _ = shop_info(row[0])
                return _resp(200, {
                    'configured': is_configured(),
                    'connected': bool(row),
                    'shop_id': row[1] if row else None,
                    'connected_at': row[4] if row else None,
                    'expires_at': row[2] if row else None,
                    'shop': shop,
                })

            if action == 'authorize_url':
                if not is_configured():
                    return _resp(200, {'success': False, 'error': 'Подключение ЮKassa ещё не настроено на платформе'})
                query = urllib.parse.urlencode({
                    'response_type': 'code',
                    'client_id': os.environ['YOOKASSA_CLIENT_ID'],
                    'state': str(company_id),
                })
                return _resp(200, {'success': True, 'authorize_url': f'{AUTHORIZE_URL}?{query}'})

            return _resp(400, {'error': 'Unknown action'})

        if method == 'POST':
            body = json.loads(event.get('body') or '{}')
            company_id = body.get('company_id')
            if not company_id:
                return _resp(400, {'error': 'company_id required'})

            if body.get('action') == 'disconnect':
                cur.execute(f'''
                    UPDATE {SCHEMA}.company_bank_oauth_grants SET revoked_at = NOW(), updated_at = NOW()
                    WHERE company_id = %s AND provider_slug = %s AND revoked_at IS NULL
                ''', (int(company_id), PROVIDER_SLUG))
                conn.commit()
                return _resp(200, {'success': True})

            code = str(body.get('code') or '').strip()
            if not code:
                return _resp(400, {'error': 'code required'})
            if not is_configured():
                return _resp(200, {'success': False, 'error': 'Подключение ЮKassa ещё не настроено на платформе'})
            token_data, err = exchange_code(code)
            if not token_data:
                return _resp(200, {'success': False, 'error': f'{err}. Код подтверждения действует 5 минут — попробуйте подключить ещё раз'})
            token = token_data['access_token']
            shop, _ = shop_info(token)
            shop_id = str((shop or {}).get('account_id') or '') or None
            expires_in = int(token_data.get('expires_in') or 0)
            cur.execute(f'''
                INSERT INTO {SCHEMA}.company_bank_oauth_grants
                    (company_id, provider_slug, is_sandbox, access_token, refresh_token, scope, expires_at)
                VALUES (%s, %s, %s, %s, NULL, %s,
                        CASE WHEN %s > 0 THEN NOW() + make_interval(secs => %s) ELSE NULL END)
                ON CONFLICT (company_id, provider_slug) DO UPDATE SET
                    is_sandbox = EXCLUDED.is_sandbox,
                    access_token = EXCLUDED.access_token,
                    scope = EXCLUDED.scope,
                    expires_at = EXCLUDED.expires_at,
                    revoked_at = NULL,
                    updated_at = NOW()
            ''', (int(company_id), PROVIDER_SLUG, bool((shop or {}).get('test')), token, shop_id,
                  expires_in, expires_in))
            conn.commit()
            return _resp(200, {'success': True, 'shop': shop})

        return _resp(405, {'error': 'Method not allowed'})
    finally:
        cur.close()
        conn.close()

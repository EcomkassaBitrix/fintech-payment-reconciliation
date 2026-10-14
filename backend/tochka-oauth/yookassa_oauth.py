import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

import psycopg2
from auth_guard import guard, is_platform_admin
import tbank_terminal

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


def _provider_row(cur, slug: str):
    cur.execute(f'''
        SELECT slug, name, description, auth_type, is_enabled, COALESCE(terminal_key, shop_id), is_test,
               token_expires_at, connected_at,
               (access_token IS NOT NULL AND (token_expires_at IS NULL OR token_expires_at > NOW()))
               OR (terminal_key IS NOT NULL AND terminal_password IS NOT NULL),
               (SELECT COALESCE(NULLIF(full_name, ''), phone) FROM {SCHEMA}.app_users WHERE id = connected_by),
               config
        FROM {SCHEMA}.platform_payment_providers WHERE slug = %s
    ''', (slug,))
    return cur.fetchone()


def _provider_json(r) -> Dict[str, Any]:
    return {
        'slug': r[0], 'name': r[1], 'description': r[2], 'auth_type': r[3], 'is_enabled': r[4],
        'shop_id': r[5], 'is_test': r[6], 'token_expires_at': r[7], 'connected_at': r[8],
        'connected': bool(r[9]), 'connected_by': r[10],
        'configured': is_configured() if r[0] == PROVIDER_SLUG else True,
        'config': r[11] or {},
    }


def yookassa_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    '''
    Провайдеры приёма оплаты платформы (раздел админки «Оплата»). Только админ платформы.
    GET  ?action=list                        -> список провайдеров и состояние подключения
    GET  ?action=authorize_url               -> ссылка на выдачу прав магазина ЮKassa платформе
    GET  ?action=check                       -> проверить магазин по токену (GET /v3/me)
    POST {code}                              -> обмен кода на токен, сохранение
    POST {action: "toggle", slug, enabled}   -> включить/выключить провайдера
    POST {action: "disconnect", slug}        -> отключить магазин
    POST {action: "save_terminal", terminal_key, terminal_password, receipt_enabled, taxation, vat}
                                             -> терминал Т‑Банка (проверяется запросом в банк)
    GET  ?action=check&slug=tbank            -> проверить терминал Т‑Банка
    '''
    denied = guard(event, check_company=False)
    if denied:
        return denied
    user_id = event.get('session_user_id')
    method = event.get('httpMethod', 'GET')
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        if not user_id or not is_platform_admin(cur, user_id):
            return _resp(403, {'error': 'Доступ только для администратора платформы'})

        if method == 'GET':
            params = event.get('queryStringParameters') or {}
            action = params.get('action') or 'list'
            if action == 'list':
                cur.execute(f'SELECT slug FROM {SCHEMA}.platform_payment_providers ORDER BY sort_order, id')
                slugs = [r[0] for r in cur.fetchall()]
                return _resp(200, {'success': True, 'providers': [_provider_json(_provider_row(cur, s)) for s in slugs]})
            if action == 'authorize_url':
                if not is_configured():
                    return _resp(200, {'success': False, 'error': 'Не заданы ключи приложения ЮKassa (YOOKASSA_CLIENT_ID / YOOKASSA_CLIENT_SECRET)'})
                query = urllib.parse.urlencode({
                    'response_type': 'code',
                    'client_id': os.environ['YOOKASSA_CLIENT_ID'],
                    'state': 'platform',
                })
                return _resp(200, {'success': True, 'authorize_url': f'{AUTHORIZE_URL}?{query}'})
            if action == 'check' and params.get('slug') == 'tbank':
                return _resp(200, tbank_terminal.check(cur))
            if action == 'check':
                cur.execute(f'SELECT access_token FROM {SCHEMA}.platform_payment_providers WHERE slug = %s', (PROVIDER_SLUG,))
                row = cur.fetchone()
                if not row or not row[0]:
                    return _resp(200, {'success': False, 'error': 'Магазин не подключён'})
                shop, code = shop_info(row[0])
                if not shop:
                    return _resp(200, {'success': False, 'error': f'ЮKassa не ответила (код {code}) — переподключите магазин'})
                return _resp(200, {'success': True, 'shop': shop})
            return _resp(400, {'error': 'Unknown action'})

        if method == 'POST':
            body = json.loads(event.get('body') or '{}')
            action = body.get('action')
            if action == 'save_terminal':
                err = tbank_terminal.save(cur, body, user_id)
                if err:
                    return _resp(200, {'success': False, 'error': err})
                conn.commit()
                return _resp(200, {'success': True, 'provider': _provider_json(_provider_row(cur, 'tbank'))})
            if action == 'toggle':
                cur.execute(f'''
                    UPDATE {SCHEMA}.platform_payment_providers SET is_enabled = %s, updated_at = NOW()
                    WHERE slug = %s RETURNING slug
                ''', (bool(body.get('enabled')), body.get('slug')))
                if not cur.fetchone():
                    return _resp(404, {'error': 'Провайдер не найден'})
                conn.commit()
                return _resp(200, {'success': True, 'provider': _provider_json(_provider_row(cur, body.get('slug')))})
            if action == 'disconnect':
                cur.execute(f'''
                    UPDATE {SCHEMA}.platform_payment_providers SET access_token = NULL, shop_id = NULL,
                        terminal_key = NULL, terminal_password = NULL,
                        token_expires_at = NULL, is_enabled = false, updated_at = NOW()
                    WHERE slug = %s
                ''', (body.get('slug'),))
                conn.commit()
                return _resp(200, {'success': True, 'provider': _provider_json(_provider_row(cur, body.get('slug')))})

            code = str(body.get('code') or '').strip()
            if not code:
                return _resp(400, {'error': 'code required'})
            if not is_configured():
                return _resp(200, {'success': False, 'error': 'Не заданы ключи приложения ЮKassa'})
            token_data, err = exchange_code(code)
            if not token_data:
                return _resp(200, {'success': False, 'error': f'{err}. Код подтверждения действует 5 минут — попробуйте подключить ещё раз'})
            token = token_data['access_token']
            shop, _ = shop_info(token)
            expires_in = int(token_data.get('expires_in') or 0)
            cur.execute(f'''
                UPDATE {SCHEMA}.platform_payment_providers SET
                    access_token = %s, shop_id = %s, is_test = %s,
                    token_expires_at = CASE WHEN %s > 0 THEN NOW() + make_interval(secs => %s) ELSE NULL END,
                    connected_at = NOW(), connected_by = %s, updated_at = NOW()
                WHERE slug = %s
            ''', (token, str((shop or {}).get('account_id') or '') or None, bool((shop or {}).get('test')),
                  expires_in, expires_in, user_id, PROVIDER_SLUG))
            conn.commit()
            return _resp(200, {'success': True, 'shop': shop})

        return _resp(405, {'error': 'Method not allowed'})
    finally:
        cur.close()
        conn.close()

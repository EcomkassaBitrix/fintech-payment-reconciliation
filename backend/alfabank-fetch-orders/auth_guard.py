'''
Общая проверка доступа для всех функций (одинаковая копия в каждой папке функции).
- Сессия: заголовок X-Session-Id -> пользователь из таблицы user_sessions.
- user_id / requester_user_id в запросе заменяются пользователем из сессии,
  поэтому подставить чужой номер пользователя нельзя.
- company_id / integration_id: пользователь должен быть активным сотрудником компании.
- Служебные вызовы функций друг другом: заголовок X-Service-Sign
  (заголовки со словами key/auth платформа вырезает по пути).
'''
import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Dict, Iterable, Optional

import psycopg2

SCHEMA = 't_p83864310_fintech_payment_reco'
SESSION_DAYS = 30
CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id, X-Service-Sign, X-Cron-Token, X-User-Id, X-Auth-Token',
    'Access-Control-Max-Age': '86400'
}
_internal_key_cache: Dict[str, str] = {}


def _deny(status: int, error: str, code: str) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({'error': error, 'error_code': code}, ensure_ascii=False),
        'isBase64Encoded': False
    }


def _connect():
    return psycopg2.connect(os.environ['DATABASE_URL'])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def internal_key() -> str:
    if 'key' not in _internal_key_cache:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(f'SELECT key_value FROM {SCHEMA}.internal_keys WHERE id = 1')
            _internal_key_cache['key'] = cur.fetchone()[0]
        finally:
            conn.close()
    return _internal_key_cache['key']


def internal_headers() -> Dict[str, str]:
    '''Заголовок для вызова другой функции проекта от имени сервера.'''
    return {'X-Service-Sign': internal_key()}


def create_session(cur, user_id: int, event: Dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    ip = ((event.get('requestContext') or {}).get('identity') or {}).get('sourceIp')
    cur.execute(f'''
        INSERT INTO {SCHEMA}.user_sessions (user_id, token_hash, user_agent, ip, expires_at)
        VALUES (%s, %s, %s, %s, NOW() + INTERVAL '{SESSION_DAYS} days')
    ''', (user_id, hash_token(token), (headers.get('user-agent') or '')[:300], (ip or '')[:64]))
    return token


def revoke_session(cur, token: str) -> None:
    cur.execute(f'UPDATE {SCHEMA}.user_sessions SET revoked_at = NOW() WHERE token_hash = %s', (hash_token(token),))


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def is_platform_admin(cur, user_id: int) -> bool:
    '''Владелец компании платформы или отмеченный им сотрудник.'''
    cur.execute(f'''
        SELECT 1 FROM {SCHEMA}.company_users cu
        JOIN {SCHEMA}.companies c ON c.id = cu.company_id
        WHERE cu.user_id = %s AND cu.status = 'active' AND c.is_platform_admin = true
          AND (cu.platform_admin OR cu.role_id IN (SELECT id FROM {SCHEMA}.roles WHERE slug = 'owner'))
        LIMIT 1
    ''', (user_id,))
    return cur.fetchone() is not None


def support_access_open(cur, company_id: int, user_id: int) -> bool:
    '''Клиент открыл доступ поддержке, срок не истёк, а пользователь - админ платформы.'''
    cur.execute(f'''
        SELECT 1 FROM {SCHEMA}.companies
        WHERE id = %s AND support_access_enabled
          AND (support_access_until IS NULL OR support_access_until > NOW())
    ''', (company_id,))
    if not cur.fetchone():
        return False
    return is_platform_admin(cur, user_id)


def log_support_action(cur, company_id: int, user_id: int, method: str, action: Optional[str]) -> None:
    '''Изменения поддержки в кабинете клиента пишутся в журнал (просмотр не пишется).'''
    if method in ('GET', 'HEAD'):
        return
    details = f'{method} {action}' if action else method
    cur.execute(f'''
        INSERT INTO {SCHEMA}.support_access_log (company_id, user_id, action, details)
        VALUES (%s, %s, 'change', %s)
    ''', (company_id, user_id, details[:200]))


def guard(event: Dict[str, Any], *, public: bool = False, public_methods: Iterable[str] = (),
          public_actions: Iterable[str] = (), public_query: Iterable[str] = (),
          check_company: bool = True,
          override: Iterable[str] = ('user_id', 'requester_user_id'),
          roles: Optional[Iterable[str]] = None) -> Optional[Dict[str, Any]]:
    '''
    Возвращает готовый ответ (CORS или отказ) либо None, если запрос можно выполнять.
    Изменяет event: подставляет пользователя из сессии в параметры и тело.
    '''
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    params = event.get('queryStringParameters') or {}
    raw_body = event.get('body')
    body: Any = None
    if raw_body:
        try:
            body = json.loads(raw_body)
        except (TypeError, ValueError):
            body = None
    action = (body.get('action') if isinstance(body, dict) else None) or params.get('action')

    if public or method in public_methods or (action and action in public_actions) \
            or any(params.get(k) == '1' for k in public_query):
        return None

    given_key = headers.get('x-service-sign')
    if given_key and hmac.compare_digest(given_key, internal_key()):
        return None

    token = headers.get('x-session-id') or ''
    if not token:
        return _deny(401, 'Войдите в систему', 'session_required')

    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(f'''
            UPDATE {SCHEMA}.user_sessions SET last_seen_at = NOW()
            WHERE token_hash = %s AND revoked_at IS NULL AND expires_at > NOW()
            RETURNING user_id
        ''', (hash_token(token),))
        row = cur.fetchone()
        conn.commit()
        if not row:
            return _deny(401, 'Сессия истекла, войдите снова', 'session_required')
        user_id = row[0]

        for key in override:
            if key in params:
                params[key] = str(user_id)
            if isinstance(body, dict) and key in body:
                body[key] = user_id
        event['queryStringParameters'] = params or event.get('queryStringParameters')
        event['session_user_id'] = user_id

        if check_company:
            company_ids = set()
            integration_ids = set()
            for source in (params, body if isinstance(body, dict) else {}):
                cid = _as_int(source.get('company_id'))
                if cid:
                    company_ids.add(cid)
                iid = _as_int(source.get('integration_id'))
                if iid:
                    integration_ids.add(iid)
            if integration_ids:
                cur.execute(f'SELECT id, company_id FROM {SCHEMA}.user_integrations WHERE id = ANY(%s)',
                            (list(integration_ids),))
                found = cur.fetchall()
                if len(found) != len(integration_ids):
                    return _deny(404, 'Интеграция не найдена', 'not_found')
                company_ids.update(r[1] for r in found if r[1])
            for cid in company_ids:
                cur.execute(f'''
                    SELECT r.slug FROM {SCHEMA}.company_users cu
                    JOIN {SCHEMA}.roles r ON r.id = cu.role_id
                    WHERE cu.company_id = %s AND cu.user_id = %s AND cu.status = 'active'
                ''', (cid, user_id))
                member = cur.fetchone()
                if not member and support_access_open(cur, cid, user_id):
                    member = ('admin',)
                    log_support_action(cur, cid, user_id, method, action)
                    conn.commit()
                if not member:
                    return _deny(403, 'Нет доступа к этой компании', 'forbidden')
                if roles and member[0] not in roles:
                    return _deny(403, 'Недостаточно прав для этого действия', 'forbidden')
    finally:
        conn.close()

    if isinstance(body, dict):
        event['body'] = json.dumps(body, ensure_ascii=False)
    return None
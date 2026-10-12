import json
import os
from typing import Any, Dict

import psycopg2
from auth_guard import guard, is_platform_admin, SCHEMA

DURATIONS = {'1d': 1, '7d': 7, '30d': 30, 'forever': None}


def _resp(status: int, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(data, ensure_ascii=False, default=str),
        'isBase64Encoded': False
    }


def _iso(value):
    return value.isoformat() if value else None


def _status(cur, company_id: int) -> Dict[str, Any]:
    cur.execute(f'''
        SELECT support_access_enabled AND (support_access_until IS NULL OR support_access_until > NOW()),
               support_access_until, support_access_granted_at, u.full_name
        FROM {SCHEMA}.companies c
        LEFT JOIN {SCHEMA}.app_users u ON u.id = c.support_access_granted_by
        WHERE c.id = %s
    ''', (company_id,))
    row = cur.fetchone()
    if not row:
        return {}
    cur.execute(f'''
        SELECT l.action, l.details, l.created_at, u.full_name, u.phone
        FROM {SCHEMA}.support_access_log l
        LEFT JOIN {SCHEMA}.app_users u ON u.id = l.user_id
        WHERE l.company_id = %s
        ORDER BY l.created_at DESC LIMIT 30
    ''', (company_id,))
    log = [{'action': r[0], 'details': r[1], 'created_at': _iso(r[2]), 'user_name': r[3] or r[4]}
           for r in cur.fetchall()]
    return {
        'enabled': bool(row[0]),
        'until': _iso(row[1]),
        'granted_at': _iso(row[2]),
        'granted_by': row[3],
        'log': log
    }


def support_handler(event: Dict[str, Any]) -> Dict[str, Any]:
    '''
    Доступ поддержки платформы к кабинету клиента.
    GET ?company_id= - состояние доступа и журнал (владелец или админ компании).
    POST {action: "grant", company_id, duration: 1d|7d|30d|forever} - открыть доступ.
    POST {action: "revoke", company_id} - закрыть доступ.
    GET ?admin=1 - админ платформы: компании, открывшие доступ.
    POST {action: "enter", company_id} - админ платформы входит в кабинет (запись в журнал).
    '''
    params = event.get('queryStringParameters') or {}
    raw = event.get('body') or '{}'
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
    action = body.get('action') if isinstance(body, dict) else None
    admin_mode = params.get('admin') == '1' or action == 'enter'

    if admin_mode:
        denied = guard(event, check_company=False)
    else:
        denied = guard(event, roles=('owner', 'admin'))
    if denied:
        return denied

    user_id = event.get('session_user_id')
    method = event.get('httpMethod', 'GET')
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        if admin_mode:
            if not user_id or not is_platform_admin(cur, user_id):
                return _resp(403, {'error': 'Доступ запрещён'})
            if action == 'enter':
                company_id = int(body.get('company_id') or 0)
                cur.execute(f'''
                    SELECT 1 FROM {SCHEMA}.companies WHERE id = %s AND support_access_enabled
                      AND (support_access_until IS NULL OR support_access_until > NOW())
                ''', (company_id,))
                if not cur.fetchone():
                    return _resp(403, {'error': 'Клиент не открыл доступ или срок истёк'})
                cur.execute(f'''
                    INSERT INTO {SCHEMA}.support_access_log (company_id, user_id, action, details)
                    VALUES (%s, %s, 'enter', 'Вход в кабинет')
                ''', (company_id, user_id))
                conn.commit()
                return _resp(200, {'success': True})

            cur.execute(f'''
                SELECT c.id, c.name, c.inn, c.support_access_until, c.support_access_granted_at, u.full_name, u.phone,
                       (SELECT MAX(created_at) FROM {SCHEMA}.support_access_log l
                        WHERE l.company_id = c.id AND l.user_id = %s AND l.action = 'enter')
                FROM {SCHEMA}.companies c
                LEFT JOIN {SCHEMA}.app_users u ON u.id = c.support_access_granted_by
                WHERE c.support_access_enabled
                  AND (c.support_access_until IS NULL OR c.support_access_until > NOW())
                ORDER BY c.support_access_granted_at DESC NULLS LAST
            ''', (user_id,))
            companies = [{
                'id': r[0], 'name': r[1], 'inn': r[2], 'until': _iso(r[3]), 'granted_at': _iso(r[4]),
                'granted_by': r[5] or r[6], 'last_enter_at': _iso(r[7])
            } for r in cur.fetchall()]
            return _resp(200, {'success': True, 'companies': companies})

        company_id = int((params.get('company_id') if method == 'GET' else body.get('company_id')) or 0)
        if not company_id:
            return _resp(400, {'error': 'company_id required'})

        if method == 'GET':
            return _resp(200, {'success': True, **_status(cur, company_id)})

        if action == 'grant':
            duration = body.get('duration') or '7d'
            if duration not in DURATIONS:
                return _resp(400, {'error': 'Неверный срок доступа'})
            days = DURATIONS[duration]
            cur.execute(f'''
                UPDATE {SCHEMA}.companies SET support_access_enabled = true,
                    support_access_until = {'NOW() + make_interval(days => %s)' if days else 'NULL'},
                    support_access_granted_by = %s, support_access_granted_at = NOW(), updated_at = NOW()
                WHERE id = %s
            ''', ((days, user_id, company_id) if days else (user_id, company_id)))
            label = {'1d': 'на 1 день', '7d': 'на 7 дней', '30d': 'на 30 дней', 'forever': 'бессрочно'}[duration]
            cur.execute(f'''
                INSERT INTO {SCHEMA}.support_access_log (company_id, user_id, action, details)
                VALUES (%s, %s, 'grant', %s)
            ''', (company_id, user_id, f'Доступ открыт {label}'))
            conn.commit()
            return _resp(200, {'success': True, **_status(cur, company_id)})

        if action == 'revoke':
            cur.execute(f'''
                UPDATE {SCHEMA}.companies SET support_access_enabled = false, support_access_until = NULL,
                    updated_at = NOW()
                WHERE id = %s
            ''', (company_id,))
            cur.execute(f'''
                INSERT INTO {SCHEMA}.support_access_log (company_id, user_id, action, details)
                VALUES (%s, %s, 'revoke', 'Доступ закрыт')
            ''', (company_id, user_id))
            conn.commit()
            return _resp(200, {'success': True, **_status(cur, company_id)})

        return _resp(400, {'error': 'Неизвестное действие'})
    finally:
        cur.close()
        conn.close()
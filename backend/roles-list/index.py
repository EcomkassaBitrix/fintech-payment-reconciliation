import json
import os
import re
from typing import Any, Dict

import psycopg2

from auth_guard import guard

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id',
    'Access-Control-Max-Age': '86400'
}

ROLE_COLUMNS = 'r.id, r.slug, r.name, r.description, r.color, r.modules, r.permissions, r.is_system, r.sort_order'


def respond(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {'statusCode': status, 'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
            'body': json.dumps(payload, ensure_ascii=False, default=str), 'isBase64Encoded': False}


def role_dict(row, users_count=None) -> Dict[str, Any]:
    role = {'id': row[0], 'slug': row[1], 'name': row[2], 'description': row[3], 'color': row[4],
            'modules': row[5], 'permissions': row[6], 'is_system': row[7], 'sort_order': row[8]}
    if users_count is not None:
        role['users_count'] = users_count
    return role


def is_platform_admin(cur, user_id) -> bool:
    cur.execute('''
        SELECT 1 FROM company_users cu
        JOIN companies c ON c.id = cu.company_id
        WHERE cu.user_id = %s AND cu.status = 'active' AND c.is_platform_admin = true
          AND (cu.platform_admin OR cu.role_id IN (SELECT id FROM roles WHERE slug = 'owner'))
    ''', (user_id,))
    return cur.fetchone() is not None


def public_list(scope: str) -> Dict[str, Any]:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT {ROLE_COLUMNS} FROM roles r WHERE r.scope = %s ORDER BY r.sort_order', (scope,))
        return respond(200, {'success': True, 'roles': [role_dict(r) for r in cur.fetchall()]})
    finally:
        cur.close()
        conn.close()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Роли компаний - одна функция вместо пяти.
    GET ?scope=company - список ролей для выбора при приглашении сотрудника (публично)
    Админка платформы (только администраторы платформы):
    GET ?view=admin - роли с количеством пользователей
    POST {name, description, color, modules[], permissions[]} - создать роль
    PUT {role_id, name, description, color, modules[], permissions[]} - изменить роль
    DELETE {role_id} - удалить роль (не системную и никому не назначенную)
    '''
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}
    params = event.get('queryStringParameters') or {}
    if method == 'GET' and params.get('view') != 'admin':
        return public_list(params.get('scope') or 'company')

    denied = guard(event, check_company=False)
    if denied:
        return denied
    params = event.get('queryStringParameters') or {}
    body = json.loads(event.get('body') or '{}') if method != 'GET' else {}
    requester = params.get('requester_user_id') if method == 'GET' else body.get('requester_user_id')
    if not requester:
        return respond(400, {'error': 'requester_user_id required'})
    if method not in ('GET', 'POST', 'PUT', 'DELETE'):
        return respond(405, {'error': 'Method not allowed'})

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        if not is_platform_admin(cur, requester):
            return respond(403, {'error': 'Доступ запрещён'})

        if method == 'GET':
            cur.execute(f'''
                SELECT {ROLE_COLUMNS},
                       (SELECT COUNT(*) FROM company_users WHERE role_id = r.id AND status = 'active')
                FROM roles r WHERE r.scope = 'company' ORDER BY r.sort_order
            ''')
            return respond(200, {'success': True, 'roles': [role_dict(r, r[9]) for r in cur.fetchall()]})

        if method == 'DELETE':
            role_id = body.get('role_id')
            if not role_id:
                return respond(400, {'error': 'role_id required'})
            cur.execute("SELECT is_system FROM roles WHERE id = %s AND scope = 'company'", (role_id,))
            row = cur.fetchone()
            if not row:
                return respond(404, {'error': 'Роль не найдена'})
            if row[0]:
                return respond(400, {'error': 'Системную роль нельзя удалить'})
            cur.execute("SELECT COUNT(*) FROM company_users WHERE role_id = %s AND status = 'active'", (role_id,))
            if cur.fetchone()[0] > 0:
                return respond(400, {'error': 'Роль назначена пользователям, сначала снимите её'})
            cur.execute('DELETE FROM roles WHERE id = %s', (role_id,))
            conn.commit()
            return respond(200, {'success': True})

        name = (body.get('name') or '').strip()
        if not name:
            return respond(400, {'error': 'Укажите название роли'})
        values = (name, body.get('description', ''), body.get('color') or 'bg-info',
                  json.dumps(body.get('modules') or []), json.dumps(body.get('permissions') or []))

        if method == 'PUT':
            role_id = body.get('role_id')
            if not role_id:
                return respond(400, {'error': 'role_id required'})
            cur.execute("SELECT id FROM roles WHERE id = %s AND scope = 'company'", (role_id,))
            if not cur.fetchone():
                return respond(404, {'error': 'Роль не найдена'})
            cur.execute(f'''
                UPDATE roles r SET name = %s, description = %s, color = %s, modules = %s, permissions = %s, updated_at = now()
                WHERE r.id = %s RETURNING {ROLE_COLUMNS}
            ''', (*values, role_id))
            row = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM company_users WHERE role_id = %s AND status = 'active'", (role_id,))
            users = cur.fetchone()[0]
            conn.commit()
            return respond(200, {'success': True, 'role': role_dict(row, users)})

        slug = re.sub(r'[^a-z0-9_]', '', name.lower().replace(' ', '_')) or 'role'
        cur.execute('SELECT id FROM roles WHERE slug = %s', (slug,))
        if cur.fetchone():
            slug = f'{slug}_{os.urandom(2).hex()}'
        cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM roles WHERE scope = 'company'")
        next_sort = cur.fetchone()[0]
        cur.execute(f'''
            INSERT INTO roles AS r (slug, name, description, color, scope, modules, permissions, is_system, sort_order)
            VALUES (%s, %s, %s, %s, 'company', %s, %s, false, %s)
            RETURNING {ROLE_COLUMNS}
        ''', (slug, *values, next_sort))
        row = cur.fetchone()
        conn.commit()
        return respond(200, {'success': True, 'role': role_dict(row, 0)})
    except Exception as e:
        conn.rollback()
        return respond(500, {'error': str(e)})
    finally:
        cur.close()
        conn.close()

import json
import os
import re
import psycopg2
import platform_crm_queue
from typing import Dict, Any
from auth_guard import guard

SCHEMA = 't_p83864310_fintech_payment_reco'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'PUT, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def respond(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(payload, ensure_ascii=False),
        'isBase64Encoded': False
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Обновление профиля пользователя: ФИО и email. Телефон не меняется - это
    логин для входа.
    Args: user_id, full_name (обязательно), email (опционально, пустая строка - очистить)
    Returns: success, user {user_id, phone, full_name, email}
    '''
    denied = guard(event)
    if denied:
        return denied

    method = event.get('httpMethod', 'PUT')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    if method != 'PUT':
        return respond(405, {'error': 'Method not allowed'})

    body = json.loads(event.get('body') or '{}')
    user_id = body.get('user_id')
    full_name = (body.get('full_name') or '').strip()
    email = (body.get('email') or '').strip()

    if not user_id:
        return respond(400, {'error': 'user_id required'})
    if not full_name:
        return respond(400, {'error': 'Укажите ФИО'})
    if len(full_name) > 200:
        return respond(400, {'error': 'Слишком длинное ФИО'})
    if email and not EMAIL_RE.match(email):
        return respond(400, {'error': 'Некорректный формат email'})

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        cur.execute(f'SELECT full_name, email FROM {SCHEMA}.app_users WHERE id = %s', (user_id,))
        before = cur.fetchone()
        cur.execute(f'''
            UPDATE {SCHEMA}.app_users
            SET full_name = %s, email = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id, phone, full_name, email
        ''', (full_name, email or None, user_id))
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return respond(404, {'error': 'Пользователь не найден'})
        changed = not before or (before[0] or '') != full_name or (before[1] or '') != (email or '')
        crm_queued = changed and platform_crm_queue.enqueue(cur, 'profile', user_id=row[0])
        conn.commit()
        if crm_queued:
            platform_crm_queue.signal()
        return respond(200, {
            'success': True,
            'user': {'user_id': row[0], 'phone': row[1], 'full_name': row[2], 'email': row[3]}
        })
    finally:
        cur.close()
        conn.close()

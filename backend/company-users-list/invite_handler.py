import json
import os
import re
import secrets
import psycopg2
from typing import Dict, Any
from auth_guard import guard


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Создание одноразового приглашения в компанию с назначением роли.
    Приглашение отправляется по телефону (WhatsApp/Telegram/Max) или email
    и содержит ссылку для вступления, действующую 7 дней.
    Проверяет лимит пользователей по тарифу компании.
    Args: company_id, phone, full_name, email, role_slug, channel, invited_by (user_id)
    Returns: token, expires_at для формирования ссылки-приглашения
    '''
    denied = guard(event, roles=('owner', 'admin'))
    if denied:
        return denied


    method = event.get('httpMethod', 'POST')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }

    if method != 'POST':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    body = json.loads(event.get('body', '{}'))
    company_id = body.get('company_id')
    phone_raw = body.get('phone', '')
    full_name = body.get('full_name')
    email = (body.get('email') or '').strip() or None
    role_slug = body.get('role_slug')
    channel = body.get('channel', 'telegram')
    invited_by = body.get('invited_by')

    phone = re.sub(r'\D', '', phone_raw)
    if len(phone) == 11 and phone.startswith('8'):
        phone = '7' + phone[1:]

    if not company_id or not role_slug or not phone:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'company_id, phone and role_slug required'}),
            'isBase64Encoded': False
        }

    if len(phone) != 11 or not phone.startswith('7'):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Некорректный номер телефона'}),
            'isBase64Encoded': False
        }

    if channel == 'email' and not email:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Для приглашения по email нужен адрес почты'}),
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute("SELECT id, name, color FROM roles WHERE slug = %s AND scope = 'company'", (role_slug,))
        role_row = cur.fetchone()
        if not role_row:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Role not found'}),
                'isBase64Encoded': False
            }
        role_id = role_row[0]

        cur.execute('''
            SELECT t.max_users FROM subscriptions s
            JOIN tariffs t ON t.id = s.tariff_id
            WHERE s.company_id = %s
        ''', (company_id,))
        tariff_row = cur.fetchone()
        max_users = tariff_row[0] if tariff_row else None

        if max_users is not None:
            cur.execute('''
                SELECT
                    (SELECT COUNT(*) FROM company_users WHERE company_id = %s AND status IN ('active', 'pending')) +
                    (SELECT COUNT(*) FROM invite_tokens WHERE company_id = %s AND status = 'pending' AND expires_at > now())
            ''', (company_id, company_id))
            current_count = cur.fetchone()[0]

            if current_count >= max_users:
                return {
                    'statusCode': 403,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({
                        'error': 'Лимит пользователей по тарифу исчерпан',
                        'error_code': 'limit_reached',
                        'max_users': max_users
                    }),
                    'isBase64Encoded': False
                }

        cur.execute('SELECT id FROM app_users WHERE phone = %s', (phone,))
        user_row = cur.fetchone()

        if user_row:
            cur.execute(
                'SELECT id FROM company_users WHERE company_id = %s AND user_id = %s AND status != %s',
                (company_id, user_row[0], 'removed')
            )
            if cur.fetchone():
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Пользователь уже добавлен в эту компанию'}),
                    'isBase64Encoded': False
                }

        cur.execute(
            "UPDATE invite_tokens SET status = 'cancelled', updated_at = now() WHERE company_id = %s AND phone = %s AND status = 'pending'",
            (company_id, phone)
        )

        token = secrets.token_urlsafe(32)

        cur.execute('''
            INSERT INTO invite_tokens (token, company_id, role_id, phone, email, full_name, channel, invited_by, status, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', now() + interval '7 days')
            RETURNING id, expires_at
        ''', (token, company_id, role_id, phone, email, full_name, channel, invited_by))

        invite_id, expires_at = cur.fetchone()

        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'invite_id': invite_id,
                'token': token,
                'expires_at': expires_at.isoformat()
            }),
            'isBase64Encoded': False
        }

    except Exception as e:
        conn.rollback()
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)}),
            'isBase64Encoded': False
        }
    finally:
        cur.close()
        conn.close()

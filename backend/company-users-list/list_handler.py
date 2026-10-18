import json
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Получение списка пользователей компании с их ролями,
    а также списка активных (не принятых и не истёкших) приглашений
    Args: company_id
    Returns: список пользователей компании и список приглашений
    '''
    denied = guard(event)
    if denied:
        return denied


    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }

    if method != 'GET':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    params = event.get('queryStringParameters', {}) or {}
    company_id = params.get('company_id')

    if not company_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'company_id required'}),
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT
                u.id,
                COALESCE(NULLIF(u.full_name, ''), (
                    SELECT it.full_name FROM invite_tokens it
                    WHERE it.company_id = cu.company_id
                      AND regexp_replace(it.phone, '[^0-9]', '', 'g') = regexp_replace(u.phone, '[^0-9]', '', 'g')
                      AND NULLIF(it.full_name, '') IS NOT NULL
                    ORDER BY it.created_at DESC LIMIT 1
                )) AS full_name,
                u.email, u.phone,
                r.slug, r.name, r.color,
                cu.status, cu.invited_at, cu.joined_at
            FROM company_users cu
            JOIN app_users u ON u.id = cu.user_id
            JOIN roles r ON r.id = cu.role_id
            WHERE cu.company_id = %s
            ORDER BY cu.created_at
        ''', (company_id,))

        users = []
        for row in cur.fetchall():
            users.append({
                'id': row[0],
                'full_name': row[1],
                'email': row[2],
                'phone': row[3],
                'role_slug': row[4],
                'role_name': row[5],
                'role_color': row[6],
                'status': row[7],
                'invited_at': row[8].isoformat() if row[8] else None,
                'joined_at': row[9].isoformat() if row[9] else None
            })

        cur.execute('''
            SELECT
                it.id, it.phone, it.email, it.full_name, it.channel,
                r.slug, r.name, r.color,
                it.created_at, it.expires_at
            FROM invite_tokens it
            JOIN roles r ON r.id = it.role_id
            WHERE it.company_id = %s AND it.status = 'pending' AND it.expires_at > now()
            ORDER BY it.created_at DESC
        ''', (company_id,))

        invites = []
        for row in cur.fetchall():
            invites.append({
                'id': row[0],
                'phone': row[1],
                'email': row[2],
                'full_name': row[3],
                'channel': row[4],
                'role_slug': row[5],
                'role_name': row[6],
                'role_color': row[7],
                'created_at': row[8].isoformat() if row[8] else None,
                'expires_at': row[9].isoformat() if row[9] else None
            })

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'users': users,
                'invites': invites
            }),
            'isBase64Encoded': False
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)}),
            'isBase64Encoded': False
        }
    finally:
        cur.close()
        conn.close()
import json
import re
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    GET: получение информации о приглашении по токену (компания, роль, срок действия)
    POST: принятие приглашения авторизованным пользователем — добавляет его в компанию
    с назначенной ролью. Номер телефона пользователя должен совпадать с номером
    в приглашении.
    Args (GET): token
    Args (POST): token, user_id, phone
    '''
    denied = guard(event, public_methods=('GET',))
    if denied:
        return denied


    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        if method == 'GET':
            params = event.get('queryStringParameters', {}) or {}
            token = params.get('token')

            if not token:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'token required'}),
                    'isBase64Encoded': False
                }

            cur.execute('''
                SELECT it.status, it.expires_at, it.phone, it.full_name,
                       c.name, r.name, r.color, it.channel
                FROM invite_tokens it
                JOIN companies c ON c.id = it.company_id
                JOIN roles r ON r.id = it.role_id
                WHERE it.token = %s
            ''', (token,))
            row = cur.fetchone()

            if not row:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Приглашение не найдено'}),
                    'isBase64Encoded': False
                }

            status, expires_at, phone, full_name, company_name, role_name, role_color, channel = row

            if status != 'pending':
                return {
                    'statusCode': 410,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Приглашение уже использовано или отменено'}),
                    'isBase64Encoded': False
                }

            import datetime
            if expires_at < datetime.datetime.now():
                cur.execute("UPDATE invite_tokens SET status = 'expired', updated_at = now() WHERE token = %s", (token,))
                conn.commit()
                return {
                    'statusCode': 410,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Срок действия приглашения истёк'}),
                    'isBase64Encoded': False
                }

            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'success': True,
                    'company_name': company_name,
                    'role_name': role_name,
                    'role_color': role_color,
                    'phone': phone,
                    'full_name': full_name,
                    'channel': channel,
                    'expires_at': expires_at.isoformat()
                }),
                'isBase64Encoded': False
            }

        elif method == 'POST':
            body = json.loads(event.get('body', '{}'))
            token = body.get('token')
            user_id = body.get('user_id')
            phone = body.get('phone', '')

            if not token or not user_id or not phone:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'token, user_id and phone required'}),
                    'isBase64Encoded': False
                }

            cur.execute('''
                SELECT id, company_id, role_id, phone, status, expires_at, full_name
                FROM invite_tokens WHERE token = %s
            ''', (token,))
            row = cur.fetchone()

            if not row:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Приглашение не найдено'}),
                    'isBase64Encoded': False
                }

            invite_id, company_id, role_id, invite_phone, status, expires_at, invite_full_name = row

            if status != 'pending':
                # Приглашение уже принято ровно этим пользователем (например,
                # страница отправила запрос дважды подряд) - не ошибка,
                # отдаём успех повторно вместо "приглашение уже использовано".
                if status == 'accepted':
                    cur.execute(
                        'SELECT id FROM company_users WHERE company_id = %s AND user_id = %s AND status = %s',
                        (company_id, user_id, 'active')
                    )
                    if cur.fetchone():
                        return {
                            'statusCode': 200,
                            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                            'body': json.dumps({'success': True, 'company_id': company_id}),
                            'isBase64Encoded': False
                        }
                return {
                    'statusCode': 410,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Приглашение уже использовано или отменено'}),
                    'isBase64Encoded': False
                }

            import datetime
            if expires_at < datetime.datetime.now():
                cur.execute("UPDATE invite_tokens SET status = 'expired', updated_at = now() WHERE id = %s", (invite_id,))
                conn.commit()
                return {
                    'statusCode': 410,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Срок действия приглашения истёк'}),
                    'isBase64Encoded': False
                }

            if phone != invite_phone:
                return {
                    'statusCode': 403,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Это приглашение отправлено на другой номер телефона'}),
                    'isBase64Encoded': False
                }

            # Вступает только владелец номера из приглашения: пользователь должен
            # быть именно с этим телефоном (он подтвердил его кодом при входе).
            cur.execute('SELECT phone FROM app_users WHERE id = %s', (user_id,))
            owner_row = cur.fetchone()
            if not owner_row or re.sub(r'\D', '', owner_row[0] or '') != re.sub(r'\D', '', invite_phone or ''):
                return {
                    'statusCode': 403,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Это приглашение отправлено на другой номер телефона'}),
                    'isBase64Encoded': False
                }

            cur.execute(
                'SELECT id, status FROM company_users WHERE company_id = %s AND user_id = %s',
                (company_id, user_id)
            )
            existing = cur.fetchone()

            if existing:
                cur.execute(
                    "UPDATE company_users SET role_id = %s, status = 'active', joined_at = now(), updated_at = now() WHERE id = %s",
                    (role_id, existing[0])
                )
            else:
                cur.execute(
                    '''INSERT INTO company_users (company_id, user_id, role_id, status, joined_at)
                       VALUES (%s, %s, %s, 'active', now())''',
                    (company_id, user_id, role_id)
                )

            cur.execute(
                "UPDATE invite_tokens SET status = 'accepted', accepted_at = now(), updated_at = now() WHERE id = %s",
                (invite_id,)
            )

            # ФИО из приглашения - если у пользователя своё ещё не заполнено.
            if invite_full_name:
                cur.execute(
                    "UPDATE app_users SET full_name = %s WHERE id = %s AND (full_name IS NULL OR full_name = '')",
                    (invite_full_name, user_id)
                )

            conn.commit()

            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': True, 'company_id': company_id}),
                'isBase64Encoded': False
            }

        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
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
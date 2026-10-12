import json
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard


def _json(status: int, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(data, ensure_ascii=False),
        'isBase64Encoded': False
    }


def transfer_owner(requester_id, company_id, new_owner_id) -> Dict[str, Any]:
    '''Владелец передаёт роль владельца активному сотруднику, сам становится админом.'''
    if not company_id or not new_owner_id or not requester_id:
        return _json(400, {'error': 'company_id и user_id обязательны'})
    if int(new_owner_id) == int(requester_id):
        return _json(400, {'error': 'Вы уже владелец компании'})
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT r.slug FROM company_users cu JOIN roles r ON r.id = cu.role_id "
            "WHERE cu.company_id = %s AND cu.user_id = %s AND cu.status = 'active'",
            (company_id, requester_id)
        )
        row = cur.fetchone()
        if not row or row[0] != 'owner':
            return _json(403, {'error': 'Передать роль владельца может только владелец'})
        cur.execute(
            "SELECT cu.status FROM company_users cu WHERE cu.company_id = %s AND cu.user_id = %s",
            (company_id, new_owner_id)
        )
        target = cur.fetchone()
        if not target or target[0] != 'active':
            return _json(400, {'error': 'Передать роль можно только активному сотруднику компании'})
        cur.execute(
            "UPDATE company_users SET role_id = (SELECT id FROM roles WHERE slug = 'owner'), updated_at = now() "
            "WHERE company_id = %s AND user_id = %s",
            (company_id, new_owner_id)
        )
        cur.execute(
            "UPDATE company_users SET role_id = (SELECT id FROM roles WHERE slug = 'admin'), updated_at = now() "
            "WHERE company_id = %s AND user_id = %s",
            (company_id, requester_id)
        )
        conn.commit()
        return _json(200, {'success': True})
    except Exception as e:
        conn.rollback()
        return _json(500, {'error': str(e)})
    finally:
        cur.close()
        conn.close()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Обновление статуса пользователя в компании (блокировка/активация), удаление доступа,
    отмена приглашения или передача роли владельца
    Args (PUT): company_id, user_id, status  ИЛИ  action="transfer_owner", company_id, user_id (новый владелец)
    Args (DELETE): company_id, user_id  ИЛИ  invite_id (для отмены приглашения)
    '''
    denied = guard(event, override=('requester_user_id',), roles=('owner', 'admin'))
    if denied:
        return denied


    method = event.get('httpMethod', 'PUT')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }

    if method not in ('PUT', 'DELETE'):
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    body = json.loads(event.get('body', '{}'))
    company_id = body.get('company_id')
    user_id = body.get('user_id')
    invite_id = body.get('invite_id')
    status = body.get('status')

    if method == 'DELETE' and invite_id and not user_id:
        dsn = os.environ['DATABASE_URL']
        conn = psycopg2.connect(dsn)
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE invite_tokens SET status = 'cancelled', updated_at = now() WHERE id = %s AND company_id = %s AND status = 'pending'",
                (invite_id, company_id)
            )
            if cur.rowcount == 0:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Invite not found'}),
                    'isBase64Encoded': False
                }
            conn.commit()
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': True}),
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

    if method == 'PUT' and body.get('action') == 'transfer_owner':
        return transfer_owner(event.get('session_user_id'), company_id, user_id)

    if not company_id or not user_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'company_id and user_id required'}),
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute(
            'SELECT r.slug FROM company_users cu JOIN roles r ON r.id = cu.role_id WHERE cu.company_id = %s AND cu.user_id = %s',
            (company_id, user_id)
        )
        row = cur.fetchone()
        if not row:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Access not found'}),
                'isBase64Encoded': False
            }

        if row[0] == 'owner':
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Нельзя изменить доступ владельца компании'}),
                'isBase64Encoded': False
            }

        if method == 'DELETE':
            cur.execute(
                "UPDATE company_users SET status = 'removed', updated_at = now() WHERE company_id = %s AND user_id = %s",
                (company_id, user_id)
            )
        else:
            if not status:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'status required'}),
                    'isBase64Encoded': False
                }
            cur.execute(
                'UPDATE company_users SET status = %s, updated_at = now() WHERE company_id = %s AND user_id = %s',
                (status, company_id, user_id)
            )

        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'success': True}),
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
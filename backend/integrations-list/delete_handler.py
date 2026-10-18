import json
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Мягкое удаление интеграции пользователя: статус меняется на 'deleted',
    сама запись и вся история (вебхуки, платежи, чеки, сделки CRM, банковские
    операции) остаются в базе нетронутыми - события в ленте и данные сверки
    не пропадают задним числом. Из личного кабинета (integrations-list) такая
    интеграция скрывается, а webhook-receive перестаёт принимать по ней хуки
    (фильтр status='active').
    '''
    denied = guard(event)
    if denied:
        return denied

    
    method = event.get('httpMethod', 'DELETE')
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-User-Id',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }
    
    if method != 'DELETE':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }
    
    body_str = event.get('body', '{}')
    if body_str:
        body = json.loads(body_str)
    else:
        body = {}
    
    integration_id = body.get('integration_id')
    company_id = body.get('company_id')
    
    if not integration_id or not company_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'integration_id and company_id required'}),
            'isBase64Encoded': False
        }
    
    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT id FROM user_integrations
            WHERE id = %s AND company_id = %s
        ''', (integration_id, company_id))
        
        exists = cur.fetchone()
        
        if not exists:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Integration not found or access denied'}),
                'isBase64Encoded': False
            }
        
        # Мягкое удаление: статус -> 'deleted', история не трогается. Новый
        # webhook_token не выдаём, а старый обнуляем, чтобы освободить
        # уникальность и исключить приём хуков по старому URL в любом случае
        # (webhook-receive и так фильтрует по status='active', это подстраховка).
        cur.execute('''
            UPDATE user_integrations
            SET status = 'deleted',
                webhook_token = webhook_token || '_deleted_' || id::text,
                updated_at = NOW()
            WHERE id = %s
        ''', (integration_id,))

        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'message': 'Integration deleted successfully'
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
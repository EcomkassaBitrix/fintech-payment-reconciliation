import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any
import psycopg2
from auth_guard import guard

SCHEMA = 't_p83864310_fintech_payment_reco'
DEFAULT_MESSENGER_URL = 'https://functions.poehali.dev/ace36e55-b169-41f2-9d2b-546f92221bb7'


def messenger_url() -> str:
    '''Адрес сервиса сообщений и писем: из настроек платформы, иначе по умолчанию.'''
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        cur = conn.cursor()
        cur.execute(f'SELECT messenger_api_url FROM {SCHEMA}.platform_settings WHERE id = 1')
        row = cur.fetchone()
        return (row[0] if row and row[0] else DEFAULT_MESSENGER_URL).strip()
    finally:
        conn.close()

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Отправка сообщений в мессенджеры через API (WhatsApp/Telegram/Max)
    Принимает: provider (ek_max/ek_wa/ek_tg), recipient (номер телефона), message (текст)
    Возвращает: результат отправки с ID сообщения
    '''
    denied = guard(event, check_company=False)
    if denied:
        return denied

    method: str = event.get('httpMethod', 'POST')
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-User-Id, X-Auth-Token',
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
    
    api_key = os.environ.get('MESSENGER_API_KEY', '')
    if not api_key:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'MESSENGER_API_KEY not configured'}),
            'isBase64Encoded': False
        }
    
    try:
        body_data = json.loads(event.get('body', '{}'))
        
        provider = body_data.get('provider')
        recipient = body_data.get('recipient')
        message = body_data.get('message')
        
        if not all([provider, recipient, message]):
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Missing required fields: provider, recipient, message'}),
                'isBase64Encoded': False
            }
        
        api_url = messenger_url()
        
        payload = {
            'provider': provider,
            'recipient': recipient,
            'message': message
        }
        
        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json',
                'X-Api-Key': api_key
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'success': True,
                    'message_id': response_data.get('id', 'unknown'),
                    'provider': provider,
                    'recipient': recipient
                }),
                'isBase64Encoded': False
            }
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        return {
            'statusCode': e.code,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'error': f'Messenger API error: {e.code}',
                'details': error_body
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
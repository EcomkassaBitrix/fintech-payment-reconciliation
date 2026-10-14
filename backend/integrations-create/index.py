import json
import os
import secrets
import psycopg2
from typing import Dict, Any
from auth_guard import guard
import credentials_check

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Создание новой интеграции для компании
    Генерирует уникальный webhook_token и возвращает URL для настройки
    '''
    denied = guard(event)
    if denied:
        return denied

    
    method = event.get('httpMethod', 'POST')
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-User-Id',
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
    provider_slug = body.get('provider_slug')
    integration_name = body.get('integration_name', '')
    config = body.get('config', {})
    forward_url = body.get('forward_url', '')
    sync_interval_hours = body.get('sync_interval_hours')
    webhook_settings = body.get('webhook_settings', {
        'notify_on_authorized': True,
        'notify_on_confirmed': True,
        'notify_on_rejected': True,
        'notify_on_refunded': True,
        'notify_on_canceled': True
    })
    
    if not company_id or not provider_slug:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'company_id and provider_slug required'}),
            'isBase64Encoded': False
        }
    
    webhook_token = secrets.token_urlsafe(32)
    
    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT id FROM integration_providers 
            WHERE slug = %s AND status = 'active'
        ''', (provider_slug,))
        
        provider_row = cur.fetchone()
        if not provider_row:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Provider not found'}),
                'isBase64Encoded': False
            }
        
        provider_id = provider_row[0]

        # Логин/пароль платёжки проверяем у банка до сохранения (см. credentials_check).
        creds_ok, creds_message = credentials_check.check(provider_slug, config or {})
        if not creds_ok:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': creds_message, 'error_code': 'invalid_credentials'}, ensure_ascii=False),
                'isBase64Encoded': False
            }

        if provider_slug == 'ofdru':
            # Сервер ОФД - всегда боевой, ИНН - из карточки компании: пользователь их не вводит.
            cur.execute('SELECT inn FROM companies WHERE id = %s', (company_id,))
            company_inn = ((cur.fetchone() or [None])[0] or '').strip()
            if not company_inn:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'У компании не указан ИНН - заполните его в настройках компании'}, ensure_ascii=False),
                    'isBase64Encoded': False
                }
            config = {**(config or {}), 'api_url': 'https://ofd.ru', 'inn': company_inn}

        # Лимит интеграций по тарифу (пусто - без ограничения).
        cur.execute('''
            SELECT t.max_integrations,
                   (SELECT COUNT(*) FROM user_integrations ui WHERE ui.company_id = %s AND ui.status NOT IN ('deleted', 'hidden'))
            FROM subscriptions s JOIN tariffs t ON t.id = s.tariff_id
            WHERE s.company_id = %s
        ''', (company_id, company_id))
        limit_row = cur.fetchone()
        if limit_row and limit_row[0] is not None and limit_row[1] >= limit_row[0]:
            return {
                'statusCode': 403,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'error': f'Лимит интеграций по тарифу исчерпан ({limit_row[0]}). Смените тариф или удалите неиспользуемую интеграцию.',
                    'error_code': 'limit_reached'
                }, ensure_ascii=False),
                'isBase64Encoded': False
            }

        cur.execute('''
            INSERT INTO user_integrations 
            (company_id, provider_id, integration_name, webhook_token, config, webhook_settings, forward_url, sync_interval_hours, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active')
            RETURNING id, webhook_token
        ''', (
            company_id,
            provider_id, 
            integration_name, 
            webhook_token,
            json.dumps(config),
            json.dumps(webhook_settings),
            forward_url if forward_url else None,
            sync_interval_hours
        ))
        
        integration_id, token = cur.fetchone()
        conn.commit()
        
        webhook_url = f"https://functions.poehali.dev/a923b457-57a6-4eb2-b566-9a9d65cb04e8?token={token}"
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'integration_id': integration_id,
                'webhook_url': webhook_url,
                'webhook_token': token,
                'warning': creds_message
            }, ensure_ascii=False),
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
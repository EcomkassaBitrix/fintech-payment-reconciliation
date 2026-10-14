import json
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard, is_platform_admin
import credentials_check

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Обновление настроек интеграции пользователя
    '''
    denied = guard(event)
    if denied:
        return denied

    
    method = event.get('httpMethod', 'PUT')
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'PUT, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-User-Id',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }
    
    if method != 'PUT':
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
    integration_name = body.get('integration_name')
    config = body.get('config', {})
    webhook_settings = body.get('webhook_settings', {})
    forward_url = body.get('forward_url')
    sync_interval_hours = body.get('sync_interval_hours')
    
    if body.get('action') == 'restore_hidden':
        return restore_hidden(event, integration_id, company_id)

    new_status = body.get('status')
    if integration_id and company_id and new_status in ('active', 'inactive') and set(body) <= {'integration_id', 'company_id', 'status'}:
        # Переключатель «включить/выключить»: выключенная интеграция не принимает вебхуки и не синхронизируется.
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        try:
            cur.execute('''
                UPDATE user_integrations SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND company_id = %s AND status IN ('active', 'inactive')
                RETURNING id
            ''', (new_status, integration_id, company_id))
            updated = cur.fetchone()
            conn.commit()
        finally:
            cur.close()
            conn.close()
        return {
            'statusCode': 200 if updated else 404,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'success': bool(updated), 'status': new_status} if updated else {'error': 'Integration not found or access denied'}),
            'isBase64Encoded': False
        }

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

    creds_message = None
    if config:
        cur.execute('''
            SELECT p.slug, ui.config FROM user_integrations ui
            JOIN integration_providers p ON p.id = ui.provider_id
            WHERE ui.id = %s AND ui.company_id = %s
        ''', (integration_id, company_id))
        row = cur.fetchone()
        if row:
            saved = row[1] if isinstance(row[1], dict) else json.loads(row[1] or '{}')
            new_config = {**saved, **config}
            # Проверяем у банка, только если поменялись данные входа - лишних запросов при правке названия нет.
            if any(new_config.get(k) != saved.get(k) for k in new_config):
                creds_ok, creds_message = credentials_check.check(row[0], new_config)
                if not creds_ok:
                    cur.close()
                    conn.close()
                    return {
                        'statusCode': 400,
                        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                        'body': json.dumps({'error': creds_message, 'error_code': 'invalid_credentials'}, ensure_ascii=False),
                        'isBase64Encoded': False
                    }

    try:
        cur.execute('''
            UPDATE user_integrations
            SET 
                integration_name = COALESCE(%s, integration_name),
                config = CASE WHEN %s::jsonb IS NULL THEN config
                              WHEN provider_id = (SELECT id FROM integration_providers WHERE slug = 'ofdru')
                              THEN %s::jsonb || jsonb_build_object('api_url', 'https://ofd.ru',
                                   'inn', COALESCE((SELECT inn FROM companies WHERE id = %s), config->>'inn'))
                              ELSE %s::jsonb END,
                webhook_settings = COALESCE(%s::jsonb, webhook_settings),
                forward_url = %s,
                sync_interval_hours = COALESCE(%s, sync_interval_hours),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND company_id = %s
            RETURNING id
        ''', (
            integration_name,
            json.dumps(config) if config else None,
            json.dumps(config) if config else None,
            company_id,
            json.dumps(config) if config else None,
            json.dumps(webhook_settings) if webhook_settings else None,
            forward_url,
            sync_interval_hours,
            integration_id,
            company_id
        ))
        
        updated = cur.fetchone()
        
        if not updated:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Integration not found or access denied'}),
                'isBase64Encoded': False
            }
        
        conn.commit()
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'message': 'Integration updated successfully',
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

def _json(status: int, data: Dict[str, Any]) -> Dict[str, Any]:
    return {'statusCode': status, 'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps(data, ensure_ascii=False), 'isBase64Encoded': False}


def restore_hidden(event: Dict[str, Any], integration_id, company_id) -> Dict[str, Any]:
    '''Админ платформы возвращает интеграцию, скрытую при переходе на тариф ниже, вместе с её сценариями.'''
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        if not is_platform_admin(cur, event.get('session_user_id')):
            return _json(403, {'error': 'Восстановить может только администратор платформы'})
        cur.execute('''
            SELECT t.max_integrations,
                   (SELECT COUNT(*) FROM user_integrations ui
                    WHERE ui.company_id = %s AND ui.status NOT IN ('deleted', 'hidden'))
            FROM subscriptions s JOIN tariffs t ON t.id = s.tariff_id WHERE s.company_id = %s
        ''', (company_id, company_id))
        row = cur.fetchone()
        if row and row[0] is not None and row[1] >= row[0]:
            return _json(400, {'error': f'По тарифу компании доступно интеграций: {row[0]}, уже подключено {row[1]}. '
                                         'Сначала переведите компанию на тариф выше'})
        cur.execute('''
            UPDATE user_integrations
            SET status = COALESCE(hidden_prev_status, 'active'), hidden_at = NULL, hidden_prev_status = NULL,
                updated_at = NOW()
            WHERE id = %s AND company_id = %s AND status = 'hidden'
            RETURNING id
        ''', (integration_id, company_id))
        if not cur.fetchone():
            return _json(404, {'error': 'Скрытая интеграция не найдена'})
        cur.execute('''
            UPDATE automation_scenarios
            SET removed_at = NULL, status = COALESCE(hidden_prev_status, 'stopped'), hidden_at = NULL,
                hidden_prev_status = NULL, updated_at = NOW()
            WHERE company_id = %s AND hidden_at IS NOT NULL
              AND (source_integration_id = %s OR target_integration_id = %s)
              AND NOT EXISTS (
                SELECT 1 FROM user_integrations o
                WHERE o.id IN (automation_scenarios.source_integration_id, automation_scenarios.target_integration_id)
                  AND o.status IN ('hidden', 'deleted'))
            RETURNING id
        ''', (company_id, integration_id, integration_id))
        scenarios = len(cur.fetchall())
        conn.commit()
        return _json(200, {'success': True, 'restored_scenarios': scenarios})
    finally:
        cur.close()
        conn.close()

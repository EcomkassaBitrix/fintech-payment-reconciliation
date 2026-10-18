import json
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard, is_platform_admin

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Получение списка всех интеграций компании с группировкой по категориям
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
                'Access-Control-Allow-Headers': 'Content-Type, X-User-Id',
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
        user_id = event.get('session_user_id')
        show_hidden = params.get('include_hidden') == '1' and bool(user_id) and is_platform_admin(cur, user_id)
        cur.execute('''
            SELECT 
                c.id as category_id,
                c.name as category_name,
                c.slug as category_slug,
                c.icon as category_icon,
                c.description as category_description,
                p.id as provider_id,
                p.name as provider_name,
                p.slug as provider_slug,
                p.logo_url as provider_logo,
                p.description as provider_description
            FROM integration_categories c
            LEFT JOIN integration_providers p ON p.category_id = c.id AND p.status = 'active'
            ORDER BY c.sort_order, p.name
        ''')
        
        rows = cur.fetchall()
        
        categories = {}
        for row in rows:
            cat_id = row[0]
            if cat_id not in categories:
                categories[cat_id] = {
                    'id': cat_id,
                    'name': row[1],
                    'slug': row[2],
                    'icon': row[3],
                    'description': row[4],
                    'providers': []
                }
            
            if row[5]:
                categories[cat_id]['providers'].append({
                    'id': row[5],
                    'name': row[6],
                    'slug': row[7],
                    'logo_url': row[8],
                    'description': row[9]
                })
        
        cur.execute('''
            SELECT 
                ui.id,
                ui.integration_name,
                ui.webhook_token,
                ui.status,
                ui.webhook_count,
                ui.last_webhook_at,
                ui.created_at,
                p.name as provider_name,
                p.slug as provider_slug,
                c.slug as category_slug,
                ui.provider_id,
                ui.config,
                ui.webhook_settings,
                ui.forward_url,
                ui.sync_interval_hours,
                ui.last_synced_at,
                EXISTS (SELECT 1 FROM automation_scenarios s
                        WHERE s.source_integration_id = ui.id AND s.trigger_type = 'new_payment'
                          AND s.action_type IN ('create_receipt', 'create_order') AND s.status = 'active'
                          AND s.removed_at IS NULL) AS receipts_enabled,
                (SELECT json_build_object('id', s.id, 'name', s.name) FROM automation_scenarios s
                 WHERE s.source_integration_id = ui.id AND s.trigger_type = 'new_payment'
                   AND s.action_type IN ('create_receipt', 'create_order') AND s.status = 'stopped'
                   AND s.removed_at IS NULL
                 ORDER BY (s.action_type = 'create_receipt') DESC, s.updated_at DESC LIMIT 1) AS stopped_receipt_scenario,
                CASE WHEN p.slug IN ('tochka_account', 'tochka_acquiring') AND ui.config->>'auth_method' = 'oauth' THEN (
                    SELECT CASE
                        WHEN g.id IS NULL OR g.refresh_token IS NULL THEN 'missing'
                        WHEN g.revoked_at IS NOT NULL OR g.updated_at < NOW() - INTERVAL '30 days' THEN 'expired'
                        WHEN g.updated_at < NOW() - INTERVAL '25 days' THEN 'expiring'
                        ELSE 'ok' END
                    FROM (SELECT 1) one
                    LEFT JOIN company_bank_oauth_grants g ON g.company_id = ui.company_id AND g.provider_slug = 'tochka_account'
                ) END AS oauth_status,
                ui.hidden_at
            FROM user_integrations ui
            JOIN integration_providers p ON p.id = ui.provider_id
            JOIN integration_categories c ON c.id = p.category_id
            WHERE ui.company_id = %s AND ui.status != 'deleted' AND (ui.status != 'hidden' OR %s)
            ORDER BY ui.created_at DESC
        ''', (company_id, show_hidden))
        
        user_integrations = []
        for row in cur.fetchall():
            user_integrations.append({
                'id': row[0],
                'integration_name': row[1],
                'webhook_token': row[2],
                'status': row[3],
                'webhook_count': row[4],
                'last_webhook_at': row[5].isoformat() if row[5] else None,
                'created_at': row[6].isoformat() if row[6] else None,
                'provider_name': row[7],
                'provider_slug': row[8],
                'category_slug': row[9],
                'provider_id': row[10],
                'config': row[11],
                'webhook_settings': row[12],
                'forward_url': row[13],
                'sync_interval_hours': row[14],
                'last_synced_at': row[15].isoformat() if row[15] else None,
                'receipts_enabled': bool(row[16]),
                'stopped_receipt_scenario': row[17],
                'oauth_status': row[18],
                'hidden_at': row[19].isoformat() if row[19] else None
            })
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'categories': list(categories.values()),
                'user_integrations': user_integrations
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
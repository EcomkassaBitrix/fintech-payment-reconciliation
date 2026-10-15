import json
import os
import psycopg2
from typing import Dict, Any

from tbank_oauth import (
    build_authorize_url,
    exchange_code_for_token,
    is_production_configured,
    fetch_company_info
)
from auth_guard import guard

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    OAuth-обвязка T-Business ID: подключение счёта компании владельцем через "Т-Бизнес".
    GET  ?action=authorize_url&company_id=..&redirect_uri=.. -> ссылка на согласие в Т-Банке
         (пока партнёрские ключи банка не выданы - отвечает, что способ недоступен)
    POST { action: save_token, company_id, token } -> проверка токена Т-Бизнес и сохранение
    POST { action: disconnect, company_id } -> отключение токена
    POST { code, state, company_id, redirect_uri } -> обмен кода на токен, сохранение гранта
    '''
    denied = guard(event)
    if denied:
        return denied


    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        if method == 'GET':
            params = event.get('queryStringParameters', {}) or {}
            action = params.get('action')
            company_id = params.get('company_id')
            redirect_uri = params.get('redirect_uri', '')

            if not company_id:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'company_id required'}),
                    'isBase64Encoded': False
                }

            if action == 'authorize_url':
                if not is_production_configured():
                    return {
                        'statusCode': 200,
                        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                        'body': json.dumps({'error': 'Партнёрская интеграция с Т-Банком пока недоступна — подключите токен'}, ensure_ascii=False),
                        'isBase64Encoded': False
                    }

                url = build_authorize_url(redirect_uri, state=str(company_id))
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'authorize_url': url}),
                    'isBase64Encoded': False
                }

            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Unknown action'}),
                'isBase64Encoded': False
            }

        if method == 'POST':
            body = json.loads(event.get('body') or '{}')

            if body.get('action') == 'save_token':
                company_id = body.get('company_id')
                token = (body.get('token') or '').strip()
                if token.lower().startswith('bearer '):
                    token = token[7:].strip()
                if not company_id or not token:
                    return {
                        'statusCode': 400,
                        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                        'body': json.dumps({'error': 'Укажите токен Т-Бизнес'}, ensure_ascii=False),
                        'isBase64Encoded': False
                    }
                company_info = fetch_company_info(token)
                if not company_info:
                    return {
                        'statusCode': 200,
                        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                        'body': json.dumps({'success': False, 'error': 'Т-Банк не принял токен. Проверьте, что он действующий и у него есть доступ к счетам и выписке'}, ensure_ascii=False),
                        'isBase64Encoded': False
                    }
                cur.execute('''
                    INSERT INTO t_p83864310_fintech_payment_reco.company_bank_oauth_grants
                        (company_id, provider_slug, is_sandbox, access_token, refresh_token, scope, expires_at)
                    VALUES (%s, 'tbank_account', false, %s, NULL, 'manual_token', NULL)
                    ON CONFLICT (company_id, provider_slug) DO UPDATE SET
                        is_sandbox = false,
                        access_token = EXCLUDED.access_token,
                        refresh_token = NULL,
                        scope = 'manual_token',
                        expires_at = NULL,
                        revoked_at = NULL,
                        updated_at = NOW()
                ''', (company_id, token))
                conn.commit()
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'success': True, 'company_name': company_info.get('name')}, ensure_ascii=False),
                    'isBase64Encoded': False
                }

            if body.get('action') == 'disconnect':
                company_id = body.get('company_id')
                cur.execute('''
                    DELETE FROM t_p83864310_fintech_payment_reco.company_bank_oauth_grants
                    WHERE company_id = %s AND provider_slug = 'tbank_account'
                ''', (company_id,))
                conn.commit()
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'success': True}),
                    'isBase64Encoded': False
                }

            code = body.get('code')
            company_id = body.get('company_id') or body.get('state')
            redirect_uri = body.get('redirect_uri', '')

            if not code or not company_id:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'code and company_id required'}),
                    'isBase64Encoded': False
                }

            token_data = exchange_code_for_token(code, redirect_uri)
            if not token_data:
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'success': False, 'error': 'Не удалось получить токен от Т-Банка'}),
                    'isBase64Encoded': False
                }

            cur.execute('''
                INSERT INTO t_p83864310_fintech_payment_reco.company_bank_oauth_grants
                    (company_id, provider_slug, is_sandbox, access_token, refresh_token, scope, expires_at)
                VALUES (%s, 'tbank_account', false, %s, %s, %s, NOW() + (%s || ' seconds')::interval)
                ON CONFLICT (company_id, provider_slug) DO UPDATE SET
                    is_sandbox = false,
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    scope = EXCLUDED.scope,
                    expires_at = EXCLUDED.expires_at,
                    updated_at = NOW()
            ''', (
                company_id,
                token_data.get('access_token'),
                token_data.get('refresh_token'),
                token_data.get('scope'),
                str(token_data.get('expires_in', 3600))
            ))
            conn.commit()

            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': True}),
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
import json
import os
import psycopg2
from typing import Dict, Any

from tbank_oauth import fetch_company_info, fetch_accounts
from auth_guard import guard

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Проверяет, подтвердила ли компания доступ через Т-Бизнес (T-Business ID OAuth),
    и если да - возвращает список её расчётных счетов в Т-Банке для выбора
    в настройке интеграции без ручного ввода номера счёта.
    Args: company_id (query)
    Returns: is_connected (bool), company_name, accounts[]
    '''
    denied = guard(event)
    if denied:
        return denied


    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

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
            SELECT access_token
            FROM t_p83864310_fintech_payment_reco.company_bank_oauth_grants
            WHERE company_id = %s AND provider_slug = 'tbank_account' AND NOT is_sandbox
        ''', (company_id,))

        row = cur.fetchone()

        if not row:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'is_connected': False, 'accounts': []}),
                'isBase64Encoded': False
            }

        access_token = row[0]

        company_info = fetch_company_info(access_token)
        if not company_info and fetch_accounts(access_token) is not None:
            company_info = {'name': ''}
        if not company_info:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'is_connected': False, 'accounts': [], 'error': 'Не удалось проверить подтверждение Т-Бизнес'}),
                'isBase64Encoded': False
            }

        accounts = fetch_accounts(access_token) or []

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'is_connected': True,
                'company_name': company_info.get('name'),
                'inn': company_info.get('requisites', {}).get('inn'),
                'accounts': [
                    {
                        'account_number': acc.get('accountNumber'),
                        'currency': acc.get('currency'),
                        'balance': (acc.get('balance') or {}).get('otb')
                    }
                    for acc in accounts
                ]
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

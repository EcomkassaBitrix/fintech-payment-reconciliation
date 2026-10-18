import json
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Публичное получение списка активных тарифов для лендинга (без авторизации)
    Returns: список тарифов с ценами и лимитами
    '''
    denied = guard(event, public=True)
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

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT slug, name, description, price, billing_period,
                   max_companies, max_users, max_integrations, features, period_days, yearly_discount_percent, trial_days, modules
            FROM tariffs
            WHERE is_active = true
            ORDER BY sort_order
        ''')

        tariffs = []
        for row in cur.fetchall():
            tariffs.append({
                'slug': row[0],
                'name': row[1],
                'description': row[2],
                'price': float(row[3]),
                'billing_period': row[4],
                'max_companies': row[5],
                'max_users': row[6],
                'max_integrations': row[7],
                'features': row[8],
                'period_days': row[9],
                'yearly_discount_percent': float(row[10] or 0),
                'trial_days': row[11] or 0,
                'modules': row[12]
            })

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'tariffs': tariffs
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

import json
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard
from support_access import support_handler

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}

# Список часовых поясов, которые можно выбрать в настройках компании - все
# основные пояса России (страна, для которой сделан сервис) плюс UTC как
# нейтральный вариант. Список сверяется и на бэке, чтобы в колонку не могло
# попасть произвольное значение с фронта.
ALLOWED_TIMEZONES = {
    'Europe/Kaliningrad',
    'Europe/Moscow',
    'Europe/Samara',
    'Asia/Yekaterinburg',
    'Asia/Omsk',
    'Asia/Krasnoyarsk',
    'Asia/Irkutsk',
    'Asia/Yakutsk',
    'Asia/Vladivostok',
    'Asia/Magadan',
    'Asia/Kamchatka',
    'UTC'
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Обновление настроек компании (пока только часовой пояс, используемый для
    отображения дат и времени во всём интерфейсе - событиях, чеках, логах).
    Args: company_id, timezone (IANA-имя, например "Europe/Moscow")
    Returns: success, timezone
    '''
    # Доступ поддержки платформы: GET и POST - отдельный раздел (support_access.py).
    if event.get('httpMethod') in ('GET', 'POST'):
        return support_handler(event)

    denied = guard(event)
    if denied:
        return denied


    method = event.get('httpMethod', 'PUT')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    if method != 'PUT':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    body = json.loads(event.get('body') or '{}')
    company_id = body.get('company_id')
    timezone = body.get('timezone')

    if not company_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'company_id required'}),
            'isBase64Encoded': False
        }

    if not timezone or timezone not in ALLOWED_TIMEZONES:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Invalid timezone'}),
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute('''
            UPDATE t_p83864310_fintech_payment_reco.companies
            SET timezone = %s, updated_at = NOW()
            WHERE id = %s
            RETURNING id
        ''', (timezone, company_id))

        updated = cur.fetchone()
        if not updated:
            conn.rollback()
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Company not found'}),
                'isBase64Encoded': False
            }

        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'success': True, 'timezone': timezone}),
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
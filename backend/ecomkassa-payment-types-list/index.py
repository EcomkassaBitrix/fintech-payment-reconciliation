import json
import os
import urllib.request
import urllib.error
import psycopg2
from typing import Dict, Any

from ecomkassa_token import ensure_valid_token
from auth_guard import guard

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}

ECOMKASSA_BASE_URL = 'https://app.ecomkassa.ru'


def fetch_payment_types(token: str, store_id: str, protocol_version: str = 'v4') -> Any:
    '''
    GET /fiscalorder/{version}/{storeId}/paymentTypes - список видов оплат,
    настроенных в личном кабинете Екомкассы (например, "Платёж через счёт
    Я.Касса"). Ответ: [{"id": 101, "code": 1, "description": "..."}].
    '''
    # Метод есть только в v4 (в v5 Екомкасса отвечает 404), виды оплат магазина от протокола не зависят.
    url = f'{ECOMKASSA_BASE_URL}/fiscalorder/v4/{store_id}/paymentTypes'
    req = urllib.request.Request(url, headers={'Token': token})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode('utf-8'))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Получение списка видов оплат (paymentTypes), настроенных в кассе Екомкасса,
    для выбора при подключении интеграции "Екомкасса — платёжный шлюз". Токен
    и store_id берутся из уже подключённой кассы "Екомкасса" той же компании -
    у шлюза своих учётных данных нет, он работает поверх кассы.
    Args: company_id (обязателен)
    Returns: payment_types[] {id, code, description}, cash_register_connected
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
            SELECT ui.id, ui.config
            FROM t_p83864310_fintech_payment_reco.user_integrations ui
            JOIN t_p83864310_fintech_payment_reco.integration_providers p ON p.id = ui.provider_id
            WHERE ui.company_id = %s AND p.slug = 'ecomkassa' AND ui.status = 'active'
            ORDER BY ui.id
            LIMIT 1
        ''', (company_id,))

        cash_row = cur.fetchone()
        if not cash_row:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': True, 'cash_register_connected': False, 'payment_types': []}),
                'isBase64Encoded': False
            }

        cash_integration_id, cash_config = cash_row
        cash_config = json.loads(cash_config) if isinstance(cash_config, str) else (cash_config or {})
        # Токен Екомкассы живёт 24 часа - если истёк, получаем новый по
        # сохранённым логину/паролю и сразу обновляем config в БД.
        token = ensure_valid_token(cur, cash_integration_id, cash_config)
        store_id = cash_config.get('store_id')
        protocol_version = cash_config.get('protocol_version', 'v4')

        if not token or not store_id:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': True, 'cash_register_connected': False, 'payment_types': []}),
                'isBase64Encoded': False
            }

        try:
            payment_types = fetch_payment_types(token, store_id, protocol_version)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': False, 'error': 'Не удалось получить виды оплат из Екомкассы'}),
                'isBase64Encoded': False
            }

        if not isinstance(payment_types, list):
            payment_types = []

        # Справочник видов оплат общий для всех клиентов: новые виды добавляем,
        # у известных обновляем название. Привязку к коду шлюза (provider_code) не трогаем.
        for pt in payment_types:
            if not isinstance(pt, dict) or pt.get('id') is None or not pt.get('description'):
                continue
            cur.execute('''
                INSERT INTO t_p83864310_fintech_payment_reco.ecomkassa_payment_types (id, code, description)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code, description = EXCLUDED.description, updated_at = NOW()
                WHERE t_p83864310_fintech_payment_reco.ecomkassa_payment_types.description IS DISTINCT FROM EXCLUDED.description
                   OR t_p83864310_fintech_payment_reco.ecomkassa_payment_types.code IS DISTINCT FROM EXCLUDED.code
            ''', (int(pt['id']), pt.get('code'), str(pt['description'])))

        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'cash_register_connected': True,
                'payment_types': payment_types
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
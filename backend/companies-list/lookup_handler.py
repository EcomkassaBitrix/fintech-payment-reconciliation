import json
import time
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any, Optional
from auth_guard import guard

ECOMKASSA_URL = 'https://app.ecomkassa.ru/api/mobile/v1/firmInfo'
EGRUL_URL = 'https://egrul.nalog.ru/'
EGRUL_RESULT_URL = 'https://egrul.nalog.ru/search-result/'


def fetch_ecomkassa_firm_info(inn: str) -> Optional[Dict[str, Any]]:
    url = f'{ECOMKASSA_URL}/{inn}'
    req = urllib.request.Request(url, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = json.loads(response.read().decode('utf-8'))
            return body.get('payload')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def check_liquidated_in_egrul(inn: str) -> Dict[str, Any]:
    '''
    Проверка статуса компании в ЕГРЮЛ (ФНС).
    Возвращает {'checked': bool, 'liquidated': bool}.
    Если ФНС недоступен/капча/ошибка — checked=False, проверку пропускаем.
    '''
    try:
        post_data = urllib.parse.urlencode({
            'vyp3CaptchaToken': '',
            'query': inn,
            'region': '',
            'PreventChromeAutocomplete': ''
        }).encode('utf-8')

        req = urllib.request.Request(
            EGRUL_URL,
            data=post_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=8) as response:
            search_data = json.loads(response.read().decode('utf-8'))

        if search_data.get('captchaRequired'):
            return {'checked': False, 'liquidated': False}

        token = search_data.get('t')
        if not token:
            return {'checked': False, 'liquidated': False}

        time.sleep(1)

        result_req = urllib.request.Request(f'{EGRUL_RESULT_URL}{token}', method='GET')
        with urllib.request.urlopen(result_req, timeout=8) as result_response:
            result_data = json.loads(result_response.read().decode('utf-8'))

        rows = result_data.get('rows', [])
        if not rows:
            return {'checked': False, 'liquidated': False}

        row = rows[0]
        is_liquidated = bool(row.get('e'))

        return {'checked': True, 'liquidated': is_liquidated}

    except Exception:
        return {'checked': False, 'liquidated': False}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Поиск компании по ИНН через API Екомкассы + проверка ликвидации через ФНС.
    Args: inn (query param, обязателен, 10 или 12 цифр)
    Returns: данные компании (сохраняем всё), пользователю показываем только name (shortName)
    '''
    denied = guard(event, check_company=False)
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

    params = event.get('queryStringParameters') or {}
    inn = (params.get('inn') or '').strip()

    if not inn or not inn.isdigit() or len(inn) not in (10, 12):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'ИНН должен содержать 10 или 12 цифр'}),
            'isBase64Encoded': False
        }

    try:
        firm_info = fetch_ecomkassa_firm_info(inn)
    except Exception as e:
        return {
            'statusCode': 502,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': f'Сервис проверки ИНН временно недоступен: {str(e)}'}),
            'isBase64Encoded': False
        }

    if firm_info is None:
        return {
            'statusCode': 404,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Компания с таким ИНН не найдена'}),
            'isBase64Encoded': False
        }

    egrul_status = check_liquidated_in_egrul(inn)

    if egrul_status['checked'] and egrul_status['liquidated']:
        return {
            'statusCode': 409,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Компания ликвидирована и не может быть добавлена'}),
            'isBase64Encoded': False
        }

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({
            'success': True,
            'display_name': firm_info.get('shortName'),
            'company_data': {
                'inn': firm_info.get('taxId'),
                'kpp': firm_info.get('kpp'),
                'ogrn': firm_info.get('ogrn'),
                'full_name': firm_info.get('name'),
                'short_name': firm_info.get('shortName'),
                'address': firm_info.get('address')
            },
            'liquidation_check': 'confirmed_active' if egrul_status['checked'] else 'skipped'
        }),
        'isBase64Encoded': False
    }

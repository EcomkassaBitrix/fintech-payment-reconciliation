from typing import Any, Dict

import create_handler
import list_handler
import lookup_handler

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id',
    'Access-Control-Max-Age': '86400'
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Компании пользователя - одна функция вместо трёх:
    GET ?user_id= - компании пользователя
    GET ?user_id=&view=limit - сколько компаний создано и лимит по тарифу
    GET ?inn= - реквизиты организации по ИНН (для формы создания)
    POST {user_id, name, inn, ...} - создать компанию (владелец + пробная подписка)
    Каждое действие сохраняет свою проверку доступа.
    '''
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}
    params = event.get('queryStringParameters') or {}
    if method == 'POST':
        return create_handler.handler(event, context)
    if method == 'GET':
        if params.get('inn'):
            return lookup_handler.handler(event, context)
        if params.get('view') == 'limit':
            return create_handler.handler(event, context)
        return list_handler.handler(event, context)
    return {'statusCode': 405, 'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
            'body': '{"error": "Method not allowed"}', 'isBase64Encoded': False}

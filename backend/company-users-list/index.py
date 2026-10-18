import json
from typing import Any, Dict

import accept_handler
import invite_handler
import list_handler
import update_handler

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id',
    'Access-Control-Max-Age': '86400'
}


def has_invite_token(event: Dict[str, Any]) -> bool:
    '''Запрос по самому приглашению (страница приглашения): в нём всегда есть token.'''
    if (event.get('queryStringParameters') or {}).get('token'):
        return True
    try:
        body = json.loads(event.get('body') or '{}')
    except (TypeError, ValueError):
        return False
    return isinstance(body, dict) and bool(body.get('token'))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Сотрудники компании - одна функция вместо четырёх:
    GET ?company_id= - сотрудники и приглашения компании
    POST {company_id, phone, full_name, role_slug, ...} - пригласить сотрудника
    PUT / DELETE - сменить статус, передать владение, удалить сотрудника или приглашение
    Страница приглашения (запросы с token):
    GET ?token= - данные приглашения (без входа), POST {token, user_id, phone} - принять
    Каждое действие сохраняет свою проверку доступа.
    '''
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}
    if method in ('GET', 'POST') and has_invite_token(event):
        return accept_handler.handler(event, context)
    if method == 'GET':
        return list_handler.handler(event, context)
    if method == 'POST':
        return invite_handler.handler(event, context)
    if method in ('PUT', 'DELETE'):
        return update_handler.handler(event, context)
    return {'statusCode': 405, 'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
            'body': '{"error": "Method not allowed"}', 'isBase64Encoded': False}

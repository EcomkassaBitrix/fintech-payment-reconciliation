from typing import Any, Dict

import create_handler
import delete_handler
import list_handler
import update_handler

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id',
    'Access-Control-Max-Age': '86400'
}

HANDLERS = {
    'GET': list_handler.handler,
    'POST': create_handler.handler,
    'PUT': update_handler.handler,
    'DELETE': delete_handler.handler,
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Интеграции компании - одна функция вместо четырёх, действие по методу запроса:
    GET - список интеграций компании, POST - подключить, PUT - изменить (включить/выключить,
    переименовать, настройки, восстановить скрытую), DELETE - удалить.
    Вебхуки сюда не приходят - их принимает отдельная функция приёма.
    '''
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}
    target = HANDLERS.get(method)
    if not target:
        return {'statusCode': 405, 'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
                'body': '{"error": "Method not allowed"}', 'isBase64Encoded': False}
    return target(event, context)

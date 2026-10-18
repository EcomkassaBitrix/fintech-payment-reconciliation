from typing import Any, Dict

import admin_handler
import public_handler

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id',
    'Access-Control-Max-Age': '86400'
}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Тарифы - одна функция вместо двух:
    GET без параметров - публичный список тарифов (лендинг, экран "нет доступа"), без входа
    GET ?requester_user_id= / ?view=coupons|coupon_activations и любые POST - управление
    тарифами, купонами и подписками компаний (только администраторы платформы)
    Каждая часть сохраняет свою проверку доступа.
    '''
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}
    params = event.get('queryStringParameters') or {}
    if method == 'GET' and not params.get('requester_user_id') and not params.get('view'):
        return public_handler.handler(event, context)
    return admin_handler.handler(event, context)

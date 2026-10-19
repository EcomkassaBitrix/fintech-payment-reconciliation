import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from ecomkassa_token import ensure_valid_token

SCHEMA = 't_p83864310_fintech_payment_reco'
BASE_URL = 'https://app.ecomkassa.ru'


def _request(method: str, path: str, token: str, body: Optional[Dict[str, Any]] = None,
             timeout: float = 15.0) -> Tuple[int, Any]:
    data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else None
    req = urllib.request.Request(f'{BASE_URL}{path}', data=data, method=method,
                                 headers={'Token': token, 'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            text = r.read().decode('utf-8')
            status = r.status
    except urllib.error.HTTPError as e:
        text = e.read().decode('utf-8') if e.fp else ''
        status = e.code
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, str(e)
    try:
        return status, json.loads(text) if text else None
    except json.JSONDecodeError:
        return status, text


def _call(kassa: Dict[str, Any], method: str, path: str, body: Optional[Dict[str, Any]] = None,
          timeout: float = 15.0) -> Tuple[int, Any]:
    '''
    Запрос к Екомкассе от имени кассы. Если касса ответила 401/403 (токен протух или отозван
    раньше срока), интеграция сама получает новый токен по логину/паролю и повторяет запрос один раз.
    '''
    status, data = _request(method, path, kassa['token'], body, timeout)
    refresh = kassa.get('refresh')
    if status in (401, 403) and refresh:
        new_token = refresh()
        if new_token and new_token != kassa['token']:
            kassa['token'] = new_token
            status, data = _request(method, path, new_token, body, timeout)
            kassa['token_refreshed'] = True
    return status, data


def cash_register(cur, integration_id: int) -> Optional[Dict[str, Any]]:
    '''Касса Екомкассы: рабочий токен (обновляется сам), номер магазина, версия протокола.'''
    cur.execute(f'''
        SELECT ui.config, p.slug FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.id = %s AND ui.status = 'active'
    ''', (integration_id,))
    row = cur.fetchone()
    if not row or row[1] != 'ecomkassa':
        return None
    config = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
    token = ensure_valid_token(cur, integration_id, config)
    if not config.get('store_id'):
        return None
    return {'id': integration_id, 'token': token, 'store_id': str(config['store_id']),
            'protocol_version': config.get('protocol_version', 'v4'),
            'store_address': config.get('store_address') or '',
            'refresh': lambda: ensure_valid_token(cur, integration_id, config, force=True)}


def store_address(kassa: Dict[str, Any]) -> str:
    '''Адрес (место расчётов) выбранного магазина: из настроек кассы, иначе из профиля Екомкассы.'''
    if kassa.get('store_address'):
        return kassa['store_address']
    status, data = _call(kassa, 'GET', '/api/mobile/v1/profile/firm')
    stores = ((data or {}).get('payload') or {}).get('stores') if isinstance(data, dict) else None
    for st in stores or []:
        if isinstance(st, dict) and str(st.get('storeId')) == str(kassa['store_id']):
            kassa['store_address'] = st.get('storeAddress') or ''
            return kassa['store_address']
    return ''


def company_cash_register(cur, company_id: int) -> Optional[Dict[str, Any]]:
    cur.execute(f'''
        SELECT ui.id FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug = 'ecomkassa' AND ui.status = 'active'
        ORDER BY ui.id LIMIT 1
    ''', (company_id,))
    row = cur.fetchone()
    return cash_register(cur, row[0]) if row else None


def get_receipt_atol(kassa: Dict[str, Any], order_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    '''
    GET /api/mobile/v1/orders/:orderId/atol-4 (или atol-5 по протоколу кассы) -
    чек по идентификатору в формате АТОЛ Онлайн: корзина, оплаты, организация, клиент.
    '''
    formats = ['atol-5', 'atol-4'] if kassa['protocol_version'] == 'v5' else ['atol-4', 'atol-5']
    status, data = 0, None
    for fmt in formats:
        # Документ, созданный в другом формате (например, счёт ФФД 1.1 у кассы на v5),
        # Екомкасса отдаёт только в «своём» формате, в другом отвечает 404.
        status, data = _call(kassa, 'GET', f'/api/mobile/v1/orders/{order_id}/{fmt}')
        if status == 200 and isinstance(data, dict) and isinstance(data.get('receipt'), dict):
            return data, ''
        if status != 404:
            break
    return None, f'Екомкасса не отдала чек #{order_id} ({status}: {str(data)[:200]})'


def create_courier_order(kassa: Dict[str, Any], operation: str, body: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    '''
    POST /api/mobile/v1/courier/:storeId/create/:operation (sell / sell_refund) -
    создание заказа, тело как у чека продажи АТОЛ Онлайн. Повтор с тем же
    external_id возвращает уже созданный заказ, дубль не появляется.
    '''
    status, data = _call(kassa, 'POST', f"/api/mobile/v1/courier/{kassa['store_id']}/create/{operation}",
                         body, timeout=20.0)
    if status == 200 and isinstance(data, dict) and data.get('uuid') and not data.get('error'):
        return data, ''
    return None, f'Екомкасса не создала заказ ({status}: {str(data)[:300]})'


def create_fiscal_receipt(kassa: Dict[str, Any], operation: str, body: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    '''
    POST /fiscalorder/{v4|v5}/{storeId}/{operation} - чек напрямую (формат АТОЛ Онлайн):
    sell, sell_refund, sell_correction, sell_refund_correction. Касса ставит чек в очередь
    и отвечает uuid со статусом wait; итог (done/fail) приходит на callback_url.
    Повтор с тем же external_id второй чек не пробивает.
    '''
    version = kassa.get('protocol_version') or 'v4'
    status, data = _call(kassa, 'POST', f"/fiscalorder/{version}/{kassa['store_id']}/{operation}", body, timeout=20.0)
    if status == 200 and isinstance(data, dict) and data.get('uuid') and data.get('status') != 'fail':
        return data, ''
    err = (data or {}).get('error') if isinstance(data, dict) else None
    text = err.get('text') if isinstance(err, dict) else str(data)[:300]
    return None, f'Екомкасса не приняла чек ({status}: {text})'


def deliver_courier_order(kassa: Dict[str, Any], order_id: str, body: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
    '''
    POST /api/mobile/v1/courier/:orderId/deliver - подтверждение доставки (оплата) заказа.
    Тело: cashierName, paymentAddress, customerEmail, customerPhone (необязательные) и
    payments в формате АТОЛ 4 - если заказ не был предоплачен; предоплаченный - пустой массив.
    После подтверждения касса пробивает чек и шлёт callback_url заказа.
    '''
    status, data = _call(kassa, 'POST', f'/api/mobile/v1/courier/{order_id}/deliver', body, timeout=20.0)
    if status == 200 and isinstance(data, dict) and data.get('errorCode') == 0:
        return data.get('payload') or {}, ''
    return None, f'Екомкасса не подтвердила доставку заказа #{order_id} ({status}: {str(data)[:300]})'


def order_status(kassa: Dict[str, Any], order_id: str) -> Optional[str]:
    '''GET /api/mobile/v1/orders/:orderId - статус заказа (WAITING, PAID ...).'''
    status, data = _call(kassa, 'GET', f'/api/mobile/v1/orders/{order_id}')
    return data.get('status') if status == 200 and isinstance(data, dict) else None
'''
Проверка логина/пароля платёжки при сохранении интеграции.

Правило для всех банков: перед сохранением делаем безвредный запрос к API банка
с введёнными данными (статус несуществующего заказа/платежа). Банк отвечает
по-разному на «неверные данные» и «заказ не найден» - по этому и понимаем, верны ли данные.
  - неверные данные -> (False, понятная ошибка), интеграцию не сохраняем;
  - данные верные -> (True, None);
  - банк недоступен -> (True, предупреждение): сбой банка не мешает настройке.
Новый банк = функция check_<slug> + строка в CHECKERS.
'''
import hashlib
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

from russian_ca import RUSSIAN_TRUSTED_CA

Result = Tuple[bool, Optional[str]]
_ctx: Dict[str, ssl.SSLContext] = {}


def ssl_context() -> ssl.SSLContext:
    '''Серверы российских банков подписаны сертификатами Минцифры - добавляем их к системным.'''
    if 'ctx' not in _ctx:
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cadata=RUSSIAN_TRUSTED_CA)
        _ctx['ctx'] = ctx
    return _ctx['ctx']


def _post(url: str, data: bytes, content_type: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    req = urllib.request.Request(url, data=data, headers={'Content-Type': content_type}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8, context=ssl_context()) as resp:
            return json.loads(resp.read().decode('utf-8')), None
    except urllib.error.HTTPError as e:
        return None, f'банк ответил ошибкой {e.code}'
    except Exception as e:
        return None, str(e)[:120]


def _unavailable(bank: str, err: Optional[str]) -> Result:
    return True, f'Не удалось проверить данные: {bank} не ответил ({err}). Интеграция сохранена - проверьте её по первому платежу.'


TBANK_API = 'https://securepay.tinkoff.ru/v2'


def check_tbank(config: Dict[str, Any]) -> Result:
    '''
    Т-Банк эквайринг: GetState по несуществующему платежу.
    501 «Терминал не найден» - неверный Terminal ID; 204 «Неверный токен» - неверный пароль;
    любой другой ответ (например 7/325 «платёж не найден») - пара Terminal ID + пароль верна.
    '''
    terminal = str(config.get('terminal_id') or '').strip()
    password = str(config.get('terminal_password') or '').strip()
    if not terminal or not password:
        return False, 'Укажите Terminal ID и пароль терминала'
    # Номер платежа - правдоподобной длины: на короткий банк отвечает «транзакция не найдена», не проверив пароль.
    payload = {'TerminalKey': terminal, 'PaymentId': '7000000000'}
    values = {**payload, 'Password': password}
    payload['Token'] = hashlib.sha256(''.join(str(values[k]) for k in sorted(values)).encode('utf-8')).hexdigest()
    data, err = _post(f'{TBANK_API}/GetState', json.dumps(payload).encode('utf-8'), 'application/json')
    if data is None:
        return _unavailable('Т-Банк', err)
    code = str(data.get('ErrorCode') or '0')
    if code == '501':
        return False, 'Т-Банк не нашёл терминал с таким Terminal ID - проверьте его в личном кабинете'
    if code == '204':
        return False, 'Неверный пароль терминала - Т-Банк не принял пару Terminal ID + пароль'
    return True, None


ALFA_API = {
    'test': 'https://alfa.rbsuat.com/payment/rest',
    'prod': 'https://payment.alfabank.ru/payment/rest',
    'prod_pay': 'https://pay.alfabank.ru/payment/rest',
}


def check_alfabank(config: Dict[str, Any]) -> Result:
    '''
    Альфа-Банк: getOrderStatusExtended по несуществующему заказу.
    errorCode 5 «Доступ запрещён» - неверный логин/пароль или не тот сервер;
    6 «Заказ не найден» (или любой другой) - данные верны.
    '''
    user = str(config.get('user_name') or '').strip()
    password = str(config.get('password') or '').strip()
    if not user or not password:
        return False, 'Укажите логин и пароль API-пользователя'
    base = ALFA_API.get(config.get('environment') or 'prod', ALFA_API['prod'])
    form = urllib.parse.urlencode({'userName': user, 'password': password,
                                   'orderId': '00000000-0000-0000-0000-000000000000', 'language': 'ru'})
    data, err = _post(f'{base}/getOrderStatusExtended.do', form.encode('utf-8'), 'application/x-www-form-urlencoded')
    if data is None:
        return _unavailable('Альфа-Банк', err)
    if str(data.get('errorCode') or '0') == '5':
        return False, ('Альфа-Банк отказал в доступе: неверный логин или пароль, либо выбран не тот сервер банка '
                       '(логин с префиксом r- - payment.alfabank.ru, без префикса - pay.alfabank.ru)')
    return True, None


TOCHKA_API = 'https://enter.tochka.com/uapi'


def _tochka_get(path: str, token: str) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[str]]:
    req = urllib.request.Request(f'{TOCHKA_API}{path}', headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=8, context=ssl_context()) as resp:
            return json.loads(resp.read().decode('utf-8')), resp.status, None
    except urllib.error.HTTPError as e:
        return None, e.code, None
    except Exception as e:
        return None, None, str(e)[:120]


def check_tochka_acquiring(config: Dict[str, Any]) -> Result:
    '''
    Точка эквайринг: токен JWT из интернет-банка. Проверяем по списку клиентов (customers) и
    торговых точек эквайринга (retailers): 401 - токен неверный/просрочен; 403 на retailers -
    у токена нет права «Интернет-эквайринг» (без него корзину заказа не получить).
    '''
    if config.get('auth_method') == 'oauth':
        # Доступ и торговые точки уже проверены в форме через вход в Точку (tochka-oauth?action=acquiring).
        if not str(config.get('customer_code') or '').strip():
            return False, 'Подключитесь через Точку и дождитесь загрузки торговых точек'
        return True, None
    token = str(config.get('api_token') or '').strip()
    if not token:
        return False, 'Вставьте JWT-токен Точки'
    data, status, err = _tochka_get('/open-banking/v1.0/customers', token)
    if err:
        return _unavailable('Точка', err)
    if status in (401, 403):
        return False, 'Точка не приняла токен - проверьте, что он скопирован целиком и не истёк'
    codes = [c.get('customerCode') for c in ((data or {}).get('Data') or {}).get('Customer', [])
             if c.get('customerType') == 'Business' and c.get('customerCode')]
    if not codes:
        return False, 'У токена нет доступа к бизнес-клиенту Точки'
    data, status, err = _tochka_get(f'/acquiring/v1.0/retailers?customerCode={codes[0]}', token)
    if err:
        return _unavailable('Точка', err)
    if status in (401, 403):
        return False, ('У токена нет права «Интернет-эквайринг» - выпустите токен с этим разрешением '
                       '(нужно для чтения заказа и корзины)')
    retailers = ((data or {}).get('Data') or {}).get('Retailer') or []
    merchant = str(config.get('merchant_id') or '').strip()
    if merchant and retailers and not any(str(r.get('merchantId')) == merchant for r in retailers):
        return False, f'В Точке нет торговой точки с merchantId {merchant}'
    # Список точек доступен и без права на операции - проверяем само чтение операций (нужно для корзины).
    _, status, err = _tochka_get(f'/acquiring/v1.0/payments?customerCode={codes[0]}&perPage=1', token)
    if err:
        return _unavailable('Точка', err)
    if status in (401, 403):
        return False, ('У токена нет права читать операции интернет-эквайринга (ReadAcquiringData) - '
                       'выпустите в интернет-банке Точки токен с разрешением «Интернет-эквайринг»: '
                       'без него не получить корзину заказа для чека')
    return True, None


def check_bitrix24(config: Dict[str, Any]) -> Result:
    '''
    Битрикс24: нужен ВХОДЯЩИЙ вебхук портала (https://портал.bitrix24.ru/rest/1/код/).
    Частая ошибка - вставить сюда наш адрес приёма хуков (functions.poehali.dev): интеграция
    тогда не может читать сделки. Проверяем адрес и делаем безвредный запрос crm.deal.fields.
    '''
    url = str(config.get('webhook_url') or '').strip()
    if not url:
        return True, None
    if 'functions.poehali.dev' in url or '/rest/' not in url:
        return False, ('Вставлен не тот адрес. Нужен входящий вебхук из Битрикс24 вида '
                       'https://ваш-портал.bitrix24.ru/rest/1/код/ (Разработчикам → Другое → Входящий вебхук, права crm). '
                       'Наш адрес для исходящих хуков указывается в самом Битрикс24, а не здесь.')
    req = urllib.request.Request(url.rstrip('/') + '/crm.deal.fields.json', data=b'{}',
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            return False, 'Битрикс24 не принял вебхук: проверьте адрес и что у вебхука есть права crm'
        return _unavailable('Битрикс24', f'ошибка {e.code}')
    except Exception as e:
        return _unavailable('Битрикс24', str(e)[:120])
    if payload.get('error'):
        return False, f"Битрикс24: {payload.get('error_description') or payload['error']} - нужен вебхук с правами crm"
    return True, None


def check_moyklass(config: Dict[str, Any]) -> Result:
    '''«Мой Класс»: ключ API меняем на токен. 401 - неверный ключ, недоступность - предупреждение.'''
    key = str(config.get('api_key') or '').strip()
    if not key:
        return False, 'Укажите ключ API «Мой Класс»'
    req = urllib.request.Request('https://api.moyklass.com/v1/company/auth/getToken',
                                 data=json.dumps({'apiKey': key}).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8') or '{}')
        return (True, None) if data.get('accessToken') else (False, '«Мой Класс» не выдал токен по этому ключу')
    except urllib.error.HTTPError as e:
        if e.code in (400, 401, 403):
            return False, 'Неверный ключ API «Мой Класс» - проверьте его в «Настройки → API»'
        return _unavailable('«Мой Класс»', f'ошибка {e.code}')
    except Exception as e:
        return _unavailable('«Мой Класс»', str(e)[:100])


def check_yookassa(config: Dict[str, Any]) -> Result:
    '''ЮKassa: GET /v3/me по shopId + секретному ключу. 401 - неверная пара, иначе верна.'''
    import base64
    shop_id = str(config.get('shop_id') or '').strip()
    secret = str(config.get('secret_key') or '').strip()
    if not shop_id or not secret:
        return False, 'Укажите shopId и секретный ключ ЮKassa'
    if not shop_id.isdigit():
        return False, 'shopId ЮKassa состоит только из цифр - скопируйте его из раздела «Интеграция → Ключи API»'
    auth = base64.b64encode(f'{shop_id}:{secret}'.encode('utf-8')).decode('ascii')
    req = urllib.request.Request('https://api.yookassa.ru/v3/me', headers={'Authorization': f'Basic {auth}'})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8') or '{}')
        if str(data.get('account_id') or shop_id) != shop_id:
            return False, 'Секретный ключ относится к другому магазину ЮKassa'
        return True, None
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, 'ЮKassa не приняла shopId и секретный ключ - проверьте их в «Интеграция → Ключи API»'
        return _unavailable('ЮKassa', f'ошибка {e.code}')
    except Exception as e:
        return _unavailable('ЮKassa', str(e)[:100])


CHECKERS: Dict[str, Callable[[Dict[str, Any]], Result]] = {
    'tbank': check_tbank,
    'alfabank': check_alfabank,
    'yookassa': check_yookassa,
    'tochka_acquiring': check_tochka_acquiring,
    'bitrix24': check_bitrix24,
    'moyklass': check_moyklass,
}


def check(provider_slug: str, config: Dict[str, Any]) -> Result:
    checker = CHECKERS.get(provider_slug)
    return checker(config or {}) if checker else (True, None)

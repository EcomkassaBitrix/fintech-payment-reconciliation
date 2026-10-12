import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.request
import psycopg2
from typing import Dict, Any, Optional, Tuple

from auth_guard import create_session, revoke_session
import platform_crm_queue

SCHEMA = 't_p83864310_fintech_payment_reco'
DEFAULT_MESSENGER_URL = 'https://functions.poehali.dev/ace36e55-b169-41f2-9d2b-546f92221bb7'
CHANNEL_PROVIDERS = {'telegram': 'ek_tg', 'whatsapp': 'ek_wa', 'max': 'ek_max'}
CHANNEL_LABELS = {'telegram': 'Telegram', 'whatsapp': 'WhatsApp', 'max': 'Max'}
CODE_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
MAX_SENDS_PER_10_MIN = 5
CORS = {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}


def reply(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {'statusCode': status, 'headers': CORS, 'body': json.dumps(payload, ensure_ascii=False), 'isBase64Encoded': False}


def normalize_phone(raw: str) -> Optional[str]:
    phone = re.sub(r'\D', '', raw or '')
    if len(phone) == 11 and phone.startswith('8'):
        phone = '7' + phone[1:]
    return phone if len(phone) == 11 and phone.startswith('7') else None


def hash_code(phone: str, code: str) -> str:
    return hashlib.sha256(f'{phone}:{code}'.encode('utf-8')).hexdigest()


def messenger_url(cur) -> str:
    '''Адрес сервиса сообщений и писем: из настроек платформы, иначе по умолчанию.'''
    cur.execute(f'SELECT messenger_api_url FROM {SCHEMA}.platform_settings WHERE id = 1')
    row = cur.fetchone()
    return (row[0] if row and row[0] else DEFAULT_MESSENGER_URL).strip()


def send_to_messenger(channel: str, phone: str, text: str, timeout: float, url: str) -> Tuple[Optional[bool], str]:
    api_key = os.environ.get('MESSENGER_API_KEY', '')
    if not api_key:
        return False, 'Отправка сообщений не настроена'
    req = urllib.request.Request(
        url,
        data=json.dumps({'provider': CHANNEL_PROVIDERS[channel], 'recipient': phone, 'message': text}).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'X-Api-Key': api_key},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response.read()
        return True, ''
    except urllib.error.HTTPError as e:
        return False, f'{CHANNEL_LABELS[channel]} не принял сообщение (код {e.code})'
    except (TimeoutError, OSError) as e:
        if 'timed out' in str(e).lower() or isinstance(e, TimeoutError):
            return None, ''
        return False, f'Не удалось связаться с {CHANNEL_LABELS[channel]}'
    except Exception:
        return False, f'Не удалось связаться с {CHANNEL_LABELS[channel]}'


def send_code(cur, conn, body: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Шаг 1 входа: код генерируется и хранится (только хеш) на сервере,
    в браузер он не попадает. Не чаще 5 отправок на номер за 10 минут.
    '''
    phone = normalize_phone(body.get('phone', ''))
    channel = body.get('channel') or 'telegram'
    purpose = 'invite' if body.get('purpose') == 'invite' else 'login'
    if not phone:
        return reply(400, {'error': 'Некорректный номер телефона'})
    if channel not in CHANNEL_PROVIDERS:
        return reply(400, {'error': 'Неизвестный мессенджер'})

    cur.execute(f'''
        SELECT COUNT(*) FROM {SCHEMA}.auth_codes
        WHERE phone = %s AND created_at > NOW() - INTERVAL '10 minutes'
    ''', (phone,))
    if cur.fetchone()[0] >= MAX_SENDS_PER_10_MIN:
        return reply(429, {'error': 'Слишком много запросов кода. Попробуйте через 10 минут'})

    code = f'{secrets.randbelow(900000) + 100000}'
    text = (f'Ваш код для подтверждения приглашения: {code}' if purpose == 'invite'
            else f'Ваш код для входа в Сверка: {code}')

    # Код сохраняем ДО отправки: сервис сообщений может отвечать дольше, чем живёт
    # функция, а сообщение при этом всё равно доходит. Новый код отменяет прежние.
    cur.execute(f'''
        UPDATE {SCHEMA}.auth_codes SET used_at = NOW()
        WHERE phone = %s AND used_at IS NULL
    ''', (phone,))
    cur.execute(f'''
        INSERT INTO {SCHEMA}.auth_codes (phone, code_hash, channel, purpose, expires_at)
        VALUES (%s, %s, %s, %s, NOW() + INTERVAL '{CODE_TTL_MINUTES} minutes')
        RETURNING id
    ''', (phone, hash_code(phone, code), channel, purpose))
    code_id = cur.fetchone()[0]
    conn.commit()

    # Ждём ответ сервиса, пока у функции есть время (с запасом 1 с).
    try:
        remaining = context.get_remaining_time_in_millis() / 1000.0
    except Exception:
        remaining = 5.0
    ok, error = send_to_messenger(channel, phone, text, max(1.0, min(25.0, remaining - 1.0)), messenger_url(cur))
    if ok is False:
        cur.execute(f'UPDATE {SCHEMA}.auth_codes SET used_at = NOW() WHERE id = %s', (code_id,))
        conn.commit()
        return reply(502, {'error': error, 'error_code': 'send_failed'})
    return reply(200, {'success': True, 'channel': channel, 'confirmed': ok is True,
                       'expires_in': CODE_TTL_MINUTES * 60})


def check_code(cur, conn, phone: str, code: str) -> Optional[Dict[str, Any]]:
    '''
    Проверка кода: последний неиспользованный неистёкший код номера,
    не больше 5 попыток. Возвращает ответ-ошибку или None, если код верный.
    '''
    cur.execute(f'''
        SELECT id, code_hash, attempts FROM {SCHEMA}.auth_codes
        WHERE phone = %s AND used_at IS NULL AND expires_at > NOW()
        ORDER BY created_at DESC LIMIT 1
    ''', (phone,))
    row = cur.fetchone()
    if not row:
        return reply(400, {'error': 'Код истёк или не запрашивался. Запросите новый', 'error_code': 'code_expired'})
    code_id, code_hash, attempts = row
    if attempts >= MAX_ATTEMPTS:
        return reply(429, {'error': 'Превышено число попыток. Запросите новый код', 'error_code': 'too_many_attempts'})
    if not hmac.compare_digest(code_hash, hash_code(phone, re.sub(r'\D', '', code or ''))):
        cur.execute(f'UPDATE {SCHEMA}.auth_codes SET attempts = attempts + 1 WHERE id = %s RETURNING attempts', (code_id,))
        left = MAX_ATTEMPTS - cur.fetchone()[0]
        conn.commit()
        if left <= 0:
            return reply(429, {'error': 'Превышено число попыток. Запросите новый код', 'error_code': 'too_many_attempts'})
        return reply(400, {'error': f'Неверный код. Осталось попыток: {left}', 'error_code': 'wrong_code', 'attempts_left': left})
    cur.execute(f'UPDATE {SCHEMA}.auth_codes SET used_at = NOW() WHERE id = %s', (code_id,))
    return None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Вход по номеру телефона с кодом из мессенджера; код создаётся и проверяется на сервере.
    action=send: {phone, channel (telegram/whatsapp/max), purpose (login/invite)} - отправить код.
    action=verify: {phone, code, full_name?} - проверить код, найти или создать пользователя,
    открыть сессию (session_token) и вернуть данные со списком компаний.
    action=logout + X-Session-Id - закрыть сессию.
    Returns: user_id, phone, full_name, is_platform_admin, companies[]
    '''

    method = event.get('httpMethod', 'POST')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, X-Session-Id',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }

    if method != 'POST':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    body = json.loads(event.get('body') or '{}')
    action = body.get('action') or 'verify'

    if action == 'logout':
        token = {k.lower(): v for k, v in (event.get('headers') or {}).items()}.get('x-session-id')
        if token:
            conn = psycopg2.connect(os.environ['DATABASE_URL'])
            try:
                cur = conn.cursor()
                revoke_session(cur, token)
                conn.commit()
            finally:
                conn.close()
        return reply(200, {'success': True})
    full_name = body.get('full_name')
    phone = normalize_phone(body.get('phone', ''))

    if not phone:
        return reply(400, {'error': 'Некорректный номер телефона'})
    if action == 'verify' and not body.get('code'):
        return reply(400, {'error': 'Введите код из сообщения'})

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        if action == 'send':
            return send_code(cur, conn, body, context)

        error = check_code(cur, conn, phone, str(body.get('code')))
        if error:
            return error

        cur.execute('SELECT id, phone, full_name, email FROM app_users WHERE phone = %s', (phone,))
        row = cur.fetchone()

        is_new = not row
        if row:
            user_id = row[0]
            cur.execute('UPDATE app_users SET last_login_at = now() WHERE id = %s', (user_id,))
        else:
            cur.execute(
                'INSERT INTO app_users (phone, full_name, status) VALUES (%s, %s, %s) RETURNING id, phone, full_name, email',
                (phone, full_name, 'active')
            )
            row = cur.fetchone()
            user_id = row[0]

        session_token = create_session(cur, user_id, event)
        crm_queued = is_new and platform_crm_queue.enqueue(cur, 'register', user_id=user_id,
                                                           payload={'channel': body.get('channel')})
        conn.commit()
        if crm_queued:
            platform_crm_queue.signal()

        cur.execute('''
            SELECT c.id, c.name, c.status, r.slug, r.name, r.color, c.is_platform_admin, c.timezone, cu.platform_admin
            FROM company_users cu
            JOIN companies c ON c.id = cu.company_id
            JOIN roles r ON r.id = cu.role_id
            WHERE cu.user_id = %s AND cu.status = 'active'
            ORDER BY c.name
        ''', (user_id,))

        companies = []
        is_platform_admin = False
        for c_row in cur.fetchall():
            companies.append({
                'id': c_row[0],
                'name': c_row[1],
                'status': c_row[2],
                'role_slug': c_row[3],
                'role_name': c_row[4],
                'role_color': c_row[5],
                'timezone': c_row[7] or 'Europe/Moscow'
            })
            # Админка - владельцу компании платформы и отмеченным им сотрудникам.
            if c_row[6] and (c_row[3] == 'owner' or c_row[8]):
                is_platform_admin = True

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'user_id': row[0],
                'phone': row[1],
                'full_name': row[2],
                'email': row[3],
                'is_platform_admin': is_platform_admin,
                'is_new': is_new,
                'session_token': session_token,
                'companies': companies
            }),
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
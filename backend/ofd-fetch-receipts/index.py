import json
import os
import psycopg2
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
from cron_report import record_cron_run
from auth_guard import guard, subscription_guard

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}

# Автозагрузка (без явных дат, режим company_id) не тянет чеки глубже этого окна -
# страница "Чеки" дёргает загрузку при каждом открытии, поэтому большого окна не
# требуется, а маленькое держит запрос к ОФД быстрым.
AUTO_SYNC_LOOKBACK_DAYS = 3


# Источник записей для ленты «События»: крон или ручная загрузка (ставится на каждый вызов).
ORIGIN = 'manual'


def fetch_kkt_receipts(cur, integration_id: int, company_id: int, config: Dict[str, Any], kkt: str,
                       dt_from: datetime, dt_to: datetime) -> Tuple[bool, int, int, Optional[str], list]:
    '''
    Запрашивает чеки OFD.RU за период [dt_from, dt_to] по одной интеграции и
    сохраняет новые в ofd_receipts (повторные приходы игнорируются по
    UNIQUE(integration_id, receipt_id)).
    Returns: (success, total_receipts, inserted_count, error)
    '''
    inn = config.get('inn')
    auth_token = config.get('auth_token')
    api_url = config.get('api_url', 'https://ofd.ru')

    if not all([inn, kkt, auth_token]):
        return False, 0, 0, 'Missing INN, KKT or auth_token in config', []

    iso_from = dt_from.strftime('%Y-%m-%dT00:00:00')
    iso_to = dt_to.strftime('%Y-%m-%dT23:59:59')

    ofd_url = f'{api_url}/api/integration/v2/inn/{inn}/kkt/{kkt}/receipts-with-fpd-short'
    params = urllib.parse.urlencode({
        'dateFrom': iso_from,
        'dateTo': iso_to,
        'AuthToken': auth_token
    })
    full_url = f'{ofd_url}?{params}'

    try:
        req = urllib.request.Request(full_url, method='GET')
        with urllib.request.urlopen(req, timeout=30) as response:
            response_body = response.read().decode('utf-8')
            receipts_data = json.loads(response_body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else str(e)
        return False, 0, 0, f'OFD API error (РНМ {kkt}): {error_body}', []
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        return False, 0, 0, f'OFD API request failed (РНМ {kkt}): {str(e)}', []

    if isinstance(receipts_data, dict) and receipts_data.get('Status') == 'Failed':
        return False, 0, 0, f'OFD API returned error (РНМ {kkt}): {receipts_data.get("Errors", [])}', []

    if isinstance(receipts_data, dict) and 'Data' in receipts_data:
        receipts = receipts_data.get('Data', [])
    elif isinstance(receipts_data, list):
        receipts = receipts_data
    else:
        receipts = []

    # OFD.RU отдаёт DocDateTime в местном времени кассы, а в базе всё время - в UTC
    # (как у Екомкассы и платежей). Переводим из часового пояса компании.
    cur.execute('SELECT timezone FROM t_p83864310_fintech_payment_reco.companies WHERE id = %s', (company_id,))
    tz_name = ((cur.fetchone() or [None])[0] or 'Europe/Moscow')
    try:
        company_tz = ZoneInfo(tz_name)
    except Exception:
        company_tz = ZoneInfo('Europe/Moscow')

    def to_utc(value: Any) -> Any:
        if not value:
            return value
        try:
            local = datetime.fromisoformat(str(value).replace('Z', ''))
        except ValueError:
            return value
        if local.tzinfo is None:
            local = local.replace(tzinfo=company_tz)
        return local.astimezone(dt_timezone.utc).replace(tzinfo=None).isoformat()

    inserted_count = 0
    skipped: list = []
    for receipt in receipts:
        info = {
            'id': receipt.get('Id'),
            'doc_datetime': receipt.get('DocDateTime'),
            'doc_number': receipt.get('DocNumber'),
            'total': float(receipt.get('TotalSumm', 0) or 0) / 100,
            'operation_type': receipt.get('OperationType')
        }
        try:
            cur.execute('''
                INSERT INTO t_p83864310_fintech_payment_reco.ofd_receipts (
                    integration_id, company_id, receipt_id, operation_type,
                    total_sum, cash_sum, ecash_sum, doc_number, doc_datetime,
                    fn_number, raw_data, origin
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (integration_id, receipt_id) DO NOTHING
                RETURNING id
            ''', (
                integration_id,
                company_id,
                receipt.get('Id'),
                receipt.get('OperationType'),
                float(receipt.get('TotalSumm', 0)) / 100,
                float(receipt.get('CashSumm', 0)) / 100,
                float(receipt.get('ECashSumm', 0)) / 100,
                receipt.get('DocNumber'),
                to_utc(receipt.get('DocDateTime')),
                receipt.get('FnNumber'),
                json.dumps(receipt),
                ORIGIN
            ))
            if cur.fetchone():
                inserted_count += 1
            else:
                skipped.append({**info, 'reason': 'уже есть в базе (тот же Id)'})
        except Exception as e:
            skipped.append({**info, 'reason': str(e)[:200]})

    return True, len(receipts), inserted_count, None, skipped


def integration_kkts(config: Dict[str, Any]) -> list:
    '''Кассы интеграции: список kkts (несколько касс), для старых настроек - одно поле kkt.'''
    kkts = config.get('kkts')
    if isinstance(kkts, list) and kkts:
        return [str(k).strip() for k in kkts if str(k).strip()]
    return [str(config['kkt']).strip()] if config.get('kkt') else []


def fetch_and_save_receipts(cur, integration_id: int, company_id: int, config: Dict[str, Any],
                             dt_from: datetime, dt_to: datetime) -> Tuple[bool, int, int, Optional[str]]:
    '''
    Загрузка чеков OFD.RU за период по всем кассам интеграции. Ошибка одной кассы не мешает остальным.
    Returns: (success - хотя бы одна касса загрузилась, total_receipts, inserted_count, error)
    '''
    kkts = integration_kkts(config)
    if not kkts:
        fetch_and_save_receipts.last_skipped = []
        return False, 0, 0, 'Не выбрана ни одна касса'
    total, inserted, errors, skipped, ok = 0, 0, [], [], False
    for kkt in kkts:
        success, t, i, err, sk = fetch_kkt_receipts(cur, integration_id, company_id, config, kkt, dt_from, dt_to)
        total += t
        inserted += i
        skipped += sk
        ok = ok or success
        if err:
            errors.append(err)
    if ok:
        cur.execute('''
            UPDATE t_p83864310_fintech_payment_reco.user_integrations
            SET last_synced_at = NOW(), updated_at = NOW()
            WHERE id = %s
        ''', (integration_id,))
    fetch_and_save_receipts.last_skipped = skipped
    return ok, total, inserted, ('; '.join(errors) if errors else None)


def parse_iso_date(value: Optional[str], fallback: datetime) -> datetime:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return fallback


def _handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Загрузка фискальных чеков из OFD.RU.
    Два режима:
    1) integration_id + date_from/date_to (опционально) - ручная загрузка за явный
       период для одной интеграции (по умолчанию последние 30 дней).
    2) company_id - автозагрузка для ВСЕХ активных касс ОФД компании сразу, за
       период от последней успешной синхронизации (last_synced_at) до сейчас,
       но не глубже 3 дней назад. В платформе нет cron-планировщика, поэтому
       этот режим дёргается с фронта автоматически при каждом открытии
       страницы "Чеки" - без участия пользователя.
    Args: integration_id (режим 1) или company_id (режим 2), date_from/date_to (ISO, опционально)
    Returns: режим 1 - total_receipts/inserted; режим 2 - integrations_checked/total_receipts/inserted/results
    '''

    method = event.get('httpMethod', 'POST')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    if method != 'POST':
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json; charset=utf-8'},
            'body': json.dumps({'error': True, 'message': 'Запрос с заданными параметрами не поддерживается'}, ensure_ascii=False),
            'isBase64Encoded': False
        }

    body_data = json.loads(event.get('body', '{}') or '{}')
    global ORIGIN
    ORIGIN = 'cron' if body_data.get('cron_tick') else 'manual'
    integration_id = body_data.get('integration_id')
    company_id_param = body_data.get('company_id')
    date_from_param = body_data.get('date_from')
    date_to_param = body_data.get('date_to')

    if not integration_id and not company_id_param:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'integration_id or company_id required'}),
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        now = datetime.now()

        if integration_id:
            cur.execute('''
                SELECT config, company_id
                FROM t_p83864310_fintech_payment_reco.user_integrations
                WHERE id = %s AND status = 'active'
            ''', (integration_id,))

            integration_row = cur.fetchone()
            if not integration_row:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'Integration not found'}),
                    'isBase64Encoded': False
                }

            config, company_id = integration_row
            config = json.loads(config) if isinstance(config, str) else (config or {})

            dt_from = parse_iso_date(date_from_param, now - timedelta(days=30))
            dt_to = parse_iso_date(date_to_param, now)

            success, total_receipts, inserted, error = fetch_and_save_receipts(
                cur, integration_id, company_id, config, dt_from, dt_to
            )

            if not success:
                conn.rollback()
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'success': False, 'error': error}),
                    'isBase64Encoded': False
                }

            conn.commit()
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'success': True,
                    'total_receipts': total_receipts,
                    'inserted': inserted
                }),
                'isBase64Encoded': False
            }

        # Режим 2: автозагрузка по всей компании
        cur.execute('''
            SELECT ui.id, ui.config, ui.last_synced_at
            FROM t_p83864310_fintech_payment_reco.user_integrations ui
            JOIN t_p83864310_fintech_payment_reco.integration_providers p ON p.id = ui.provider_id
            WHERE ui.company_id = %s AND p.slug = 'ofdru' AND ui.status = 'active'
        ''', (company_id_param,))

        integrations = cur.fetchall()

        if not integrations:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': True, 'integrations_checked': 0, 'total_receipts': 0, 'inserted': 0, 'results': []}),
                'isBase64Encoded': False
            }

        lookback = now - timedelta(days=AUTO_SYNC_LOOKBACK_DAYS)
        total_receipts_sum = 0
        inserted_sum = 0
        results = []

        for ui_id, config, last_synced_at in integrations:
            config = json.loads(config) if isinstance(config, str) else (config or {})
            # Явный период (окно "Дозагрузка исторических данных") важнее
            # автоокна "последние 3 дня" - иначе исторические чеки ОФД не
            # запрашивались вовсе, какой бы период ни выбрал пользователь.
            if date_from_param:
                dt_from = parse_iso_date(date_from_param, lookback)
                dt_to = parse_iso_date(date_to_param, now)
            else:
                dt_from = max(last_synced_at, lookback) if last_synced_at else lookback
                dt_to = now

            success, total_receipts, inserted, error = fetch_and_save_receipts(
                cur, ui_id, company_id_param, config, dt_from, dt_to
            )

            results.append({
                'integration_id': ui_id,
                'success': success,
                'total_receipts': total_receipts,
                'inserted': inserted,
                'skipped': getattr(fetch_and_save_receipts, 'last_skipped', []),
                'error': error
            })

            if success:
                total_receipts_sum += total_receipts
                inserted_sum += inserted

        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'integrations_checked': len(integrations),
                'total_receipts': total_receipts_sum,
                'inserted': inserted_sum,
                'results': results
            }),
            'isBase64Encoded': False
        }

    except Exception as e:
        import traceback
        print('[OFD ERROR]', type(e).__name__, repr(e))
        print(traceback.format_exc())
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


def list_kkts(body: Dict[str, Any]) -> Dict[str, Any]:
    '''
    Список касс из OFD.RU по токену API и ИНН компании (GET /api/integration/v2/inn/{inn}/kkts).
    ИНН берём из карточки компании - пользователь вводит только токен.
    '''
    import ssl
    from russian_ca import RUSSIAN_TRUSTED_CA

    def reply(code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {'statusCode': code, 'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps(payload, ensure_ascii=False), 'isBase64Encoded': False}

    token = str(body.get('auth_token') or '').strip()
    company_id = body.get('company_id')
    integration_id = body.get('integration_id')
    if not company_id:
        return reply(400, {'error': 'Не выбрана компания'})
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        cur.execute('SELECT inn FROM t_p83864310_fintech_payment_reco.companies WHERE id = %s', (company_id,))
        inn = ((cur.fetchone() or [None])[0] or '').strip()
        if not token and integration_id:
            # Правка интеграции: токен уже сохранён, повторно его не просим.
            cur.execute('''SELECT config FROM t_p83864310_fintech_payment_reco.user_integrations
                           WHERE id = %s AND company_id = %s''', (integration_id, company_id))
            row = cur.fetchone()
            saved = (row[0] if row and isinstance(row[0], dict) else json.loads((row or [None])[0] or '{}'))
            token = str(saved.get('auth_token') or '')
    finally:
        cur.close()
        conn.close()
    if not inn:
        return reply(400, {'error': 'У компании не указан ИНН - заполните его в настройках компании'})
    if not token:
        return reply(400, {'error': 'Введите токен API OFD.RU'})

    ctx = ssl.create_default_context()
    ctx.load_verify_locations(cadata=RUSSIAN_TRUSTED_CA)
    url = f'https://ofd.ru/api/integration/v2/inn/{inn}/kkts?' + urllib.parse.urlencode({'AuthToken': token})
    try:
        with urllib.request.urlopen(url, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return reply(400, {'error': f'OFD.RU не принял токен для ИНН {inn}: проверьте токен и что он выдан для этой организации',
                               'error_code': 'invalid_credentials'})
        return reply(502, {'error': f'OFD.RU ответил ошибкой {e.code}'})
    except Exception as e:
        return reply(502, {'error': f'Не удалось связаться с OFD.RU: {str(e)[:120]}'})

    kkts = []
    for k in data.get('Data') or []:
        if not isinstance(k, dict) or not k.get('KktRegId'):
            continue
        kkts.append({
            'kkt': k.get('KktRegId'), 'serial': k.get('SerialNumber'), 'model': k.get('KktModel'),
            'address': k.get('FiscalAddress'), 'place': k.get('FiscalPlace'),
            'fn_end': k.get('FnEndDate'), 'contract_end': k.get('ContractEndDate'),
            'last_doc': k.get('LastDocOnKktDateTime'),
        })
    return reply(200, {'success': True, 'inn': inn, 'kkts': kkts})



def _is_db_overload(text: str) -> bool:
    return 'rate limit' in (text or '').lower()


def _handle_with_retry(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Перегрузка базы («rate limit exceeded») - временный сбой: ждём и повторяем, до 3 попыток.
    Загрузка в ОФД/банк сама идёт секунды, поэтому повторяем только если сбой случился быстро
    (в начале работы) - иначе повтор не уложится в тайм-аут функции. Повтор безопасен:
    при сбое транзакция откатывается, а дубли не пропускает уникальный ключ.
    '''
    import time
    started = time.monotonic()
    resp: Dict[str, Any] = {}
    for attempt in range(3):
        try:
            resp = _handle(event, context)
            overload = resp.get('statusCode', 200) >= 500 and _is_db_overload(str(resp.get('body')))
            error = None
        except Exception as e:
            overload, error = _is_db_overload(str(e)), e
        if not overload:
            if error:
                raise error
            return resp
        if attempt == 2 or time.monotonic() - started > 1.5:
            if error:
                raise error
            return resp
        time.sleep(0.5 * (attempt + 1))
    return resp


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''Точка входа: обработка запроса + итог для админки, если вызвал планировщик.'''
    denied = guard(event)
    if denied:
        return denied
    blocked = subscription_guard(event)
    if blocked:
        return blocked

    if event.get('httpMethod') == 'POST':
        body = json.loads(event.get('body') or '{}') or {}
        if body.get('action') == 'list_kkts':
            return list_kkts(body)

    resp = _handle_with_retry(event, context)
    if event.get('httpMethod', 'POST') == 'POST':
        record_cron_run(event, resp, 'ofd', 'inserted')
    return resp

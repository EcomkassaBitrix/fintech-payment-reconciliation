import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import urllib.request
import psycopg2
from typing import Dict, Any, List

from preparer import prepare, retry_delay, log
from ecomkassa_client import company_cash_register, _call as ecom_call
from actions import ACTIONS
from cron_report import record_cron_run
from auth_guard import guard, internal_headers

NOTIFICATIONS_URL = 'https://functions.poehali.dev/8f4541fc-6ff8-4816-a954-324e4278743d'

SCHEMA = 't_p83864310_fintech_payment_reco'
BATCH = 20

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}


def respond(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(payload, ensure_ascii=False, default=str),
        'isBase64Encoded': False
    }


def mark_failed(cur, job: Dict[str, Any], message: str, attempts: int) -> None:
    """Задание исчерпало автоповторы: статус «Не удалось» + уведомление в кабинет компании."""
    cur.execute(f'''
        UPDATE {SCHEMA}.automation_jobs SET status = 'failed', last_error = %s, locked_until = NULL, updated_at = NOW()
        WHERE id = %s
    ''', (message, job['id']))
    log(cur, job['id'], 'error', f'{message}. Попытки исчерпаны ({attempts})')
    cur.execute(f'''
        INSERT INTO {SCHEMA}.notifications (company_id, kind, level, title, message, link_module, entity_type, entity_id, payload)
        SELECT j.company_id, 'automation_failed', 'error', 'Сценарий не выполнен',
               'Сценарий «' || COALESCE(s.name, '—') || '», ' ||
               CASE WHEN j.source_type = 'payment' THEN 'платёж #' || COALESCE(wp.payment_id, j.source_id)
                    WHEN j.source_type = 'crm_deal' THEN 'сделка CRM #' || j.source_id
                    WHEN j.source_type = 'crm_lead' THEN 'лид Битрикс24 #' || j.source_id
                    WHEN j.source_type = 'ecom_invoice' THEN 'счёт Екомкассы ' || j.source_id
                    ELSE j.source_type || ' #' || j.source_id END ||
               ': ' || %s || '. Автоповторы закончились - повторите вручную в журнале автоматизации.',
               'automation', 'automation_job', j.id::text,
               jsonb_build_object('job_id', j.id, 'scenario_id', j.scenario_id, 'attempts', %s)
        FROM {SCHEMA}.automation_jobs j
        LEFT JOIN {SCHEMA}.automation_scenarios s ON s.id = j.scenario_id
        LEFT JOIN {SCHEMA}.webhook_payments wp ON j.source_type = 'payment' AND wp.id::text = j.source_id
        WHERE j.id = %s
        RETURNING id
    ''', (message, attempts, job['id']))
    row = cur.fetchone()
    if row:
        # Дубль в мессенджер/почту - тем сотрудникам компании, кто сам подписался на этот вид.
        cur.execute(f'''
            INSERT INTO {SCHEMA}.notification_deliveries (notification_id, user_id, channel)
            SELECT %s, p.user_id, p.channel
            FROM {SCHEMA}.notification_preferences p
            JOIN {SCHEMA}.company_users cu ON cu.company_id = p.company_id AND cu.user_id = p.user_id
                 AND cu.status = 'active'
            WHERE p.company_id = %s AND p.channel IS NOT NULL
            ON CONFLICT (notification_id, user_id) DO NOTHING
        ''', (row[0], job['company_id']))


def claim_jobs(cur, company_id=None, job_id=None) -> List[Dict[str, Any]]:
    '''Занимает задания на 2 минуты (SKIP LOCKED) - параллельный запуск их не возьмёт.'''
    # Задание, зависшее «в работе» (сбой посреди обработки, касса не ответила),
    # после истечения блокировки (2 мин) снова берётся в работу как обычный повтор.
    # Дубля в кассе не будет: заказ уходит с тем же external_id.
    where = ["(j.status IN ('new', 'error') AND j.next_attempt_at <= NOW() "
             "OR j.status = 'processing' AND j.locked_until < NOW())",
             '(j.locked_until IS NULL OR j.locked_until < NOW())']
    args: list = []
    if company_id:
        where.append('j.company_id = %s')
        args.append(company_id)
    if job_id:
        where = ['j.id = %s', "j.status IN ('new', 'error', 'failed', 'processing')",
                 '(j.locked_until IS NULL OR j.locked_until < NOW())']
        args = [job_id]
    cur.execute(f'''
        UPDATE {SCHEMA}.automation_jobs u SET status = 'processing', locked_until = NOW() + INTERVAL '2 minutes',
               attempts = u.attempts + 1, updated_at = NOW()
        FROM (
            SELECT j.id, j.status AS prev_status FROM {SCHEMA}.automation_jobs j
            WHERE {' AND '.join(where)}
            ORDER BY j.next_attempt_at LIMIT {BATCH}
            FOR UPDATE SKIP LOCKED
        ) c
        WHERE u.id = c.id
        RETURNING u.id, u.scenario_id, u.source_type, u.source_id, u.attempts, u.company_id, u.step, u.prepared_data,
                  c.prev_status, u.payload
    ''', args)
    return [{'id': r[0], 'scenario_id': r[1], 'source_type': r[2], 'source_id': r[3], 'attempts': r[4],
             'company_id': r[5], 'step': r[6], 'prepared_data': r[7], 'was_stuck': r[8] == 'processing',
             'payload': r[9] or {}}
            for r in cur.fetchall()]


def process_job(cur, job: Dict[str, Any]) -> str:
    cur.execute(f'''
        SELECT s.id, s.name, s.action_type, s.action_template, s.target_integration_id, s.field_mapping, s.status,
               s.removed_at, t.operation, t.paid, t.name, t.protocol_version, t.receipt_type, t.payment_method,
               t.payment_object, t.measure, t.payment_type, t.default_email,
               t.correction_type, t.correction_date_source, t.correction_base_date, t.correction_base_number,
               t.auto_deliver, t.cashier_name, t.agent_settings, t.correction_base_name, t.payment_address,
               s.correction_settings, t.vat
        FROM {SCHEMA}.automation_scenarios s
        LEFT JOIN {SCHEMA}.automation_action_templates t ON t.code = s.action_template
        WHERE s.id = %s
    ''', (job['scenario_id'],))
    r = cur.fetchone()
    scenario = {'id': r[0], 'name': r[1], 'action_type': r[2], 'action_template': r[3],
                'target_integration_id': r[4], 'field_mapping': r[5] or {},
                'template': {'operation': r[8] or 'sell', 'paid': r[9] if r[9] is not None else True,
                             'name': r[10] or r[3], 'protocol_version': r[11] or 'v4',
                             'receipt_type': r[12] or 'regular', 'payment_method': r[13],
                             'payment_object': r[14], 'measure': r[15], 'payment_type': r[16],
                             'default_email': r[17], 'correction_type': r[18],
                             'correction_date_source': r[19], 'correction_base_date': r[20],
                             'correction_base_number': r[21], 'auto_deliver': bool(r[22]),
                             'cashier_name': r[23], 'agent_settings': r[24],
                             'correction_base_name': r[25], 'payment_address': r[26],
                             'vat': r[28]}}
    # Заполненное в шаблоне действия важнее; пустые поля шаблона клиент заполняет в сценарии.
    for key, value in (r[27] or {}).items():
        if key == 'agent':
            continue
        if value in (None, '') or scenario['template'].get(key) not in (None, ''):
            continue
        scenario['template'][key] = value
    # Агентские поля: пустые в шаблоне (наименование/ИНН/телефоны поставщика и т.д.) - из сценария.
    if isinstance(scenario['template'].get('agent_settings'), dict):
        scenario['template']['agent_template'] = dict(scenario['template']['agent_settings'])
    agent_extra = (r[27] or {}).get('agent')
    if isinstance(agent_extra, dict) and isinstance(scenario['template'].get('agent_settings'), dict):
        merged = dict(scenario['template']['agent_settings'])
        for key, value in agent_extra.items():
            if value not in (None, '', []) and merged.get(key) in (None, '', []):
                merged[key] = value
        scenario['template']['agent_settings'] = merged

    if r[7] is not None:
        status, data, message = 'skipped', {}, 'Сценарий удалён'
    elif job['step'] == 'action' and job['prepared_data']:
        return run_action(cur, job, scenario, job['prepared_data'])
    else:
        try:
            status, data, message = prepare(cur, job, scenario)
        except Exception as e:
            status, data, message = 'error', {}, f'Сбой подготовки: {e}'

    if status == 'error':
        delay = retry_delay(job['attempts'])
        if delay is None:
            mark_failed(cur, job, message, job['attempts'])
            return 'failed'
        cur.execute(f'''
            UPDATE {SCHEMA}.automation_jobs SET status = 'error', last_error = %s, locked_until = NULL,
                   next_attempt_at = NOW() + (%s || ' minutes')::interval, updated_at = NOW()
            WHERE id = %s
        ''', (message, str(delay), job['id']))
        log(cur, job['id'], 'error', f'{message}. Повтор через {delay} мин (попытка {job["attempts"]})')
        return 'error'

    cur.execute(f'''
        UPDATE {SCHEMA}.automation_jobs SET status = %s, prepared_data = %s, last_error = NULL,
               locked_until = NULL, step = %s, updated_at = NOW()
        WHERE id = %s
    ''', (status, json.dumps(data, ensure_ascii=False, default=str),
          'action' if status == 'ready' else 'prepare', job['id']))
    log(cur, job['id'], 'info', message)
    if status == 'ready' and scenario['action_type'] in ACTIONS:
        return run_action(cur, job, scenario, data)
    return status


def fail_or_retry(cur, job: Dict[str, Any], message: str) -> str:
    delay = retry_delay(job['attempts'])
    if delay is None:
        mark_failed(cur, job, message, job['attempts'])
        return 'failed'
    cur.execute(f'''
        UPDATE {SCHEMA}.automation_jobs SET status = 'error', last_error = %s, locked_until = NULL,
               next_attempt_at = NOW() + (%s || ' minutes')::interval, updated_at = NOW()
        WHERE id = %s
    ''', (message, str(delay), job['id']))
    log(cur, job['id'], 'error', f'{message}. Повтор через {delay} мин (попытка {job["attempts"]})')
    return 'error'


def run_action(cur, job: Dict[str, Any], scenario: Dict[str, Any], data: Dict[str, Any]) -> str:
    '''Шаг 2: действие в кассе по собранным данным. Повтор идёт с этого шага, без повторного сбора.'''
    action = ACTIONS.get(scenario['action_type'])
    if not action:
        return 'ready'
    try:
        status, result, message = action(cur, job, scenario, data)
    except Exception as e:
        status, result, message = 'error', {}, f'Сбой действия: {e}'
    if status == 'error':
        cur.execute(f'UPDATE {SCHEMA}.automation_jobs SET step = %s WHERE id = %s', ('action', job['id']))
        log(cur, job['id'], 'error', message, result or None)
        return fail_or_retry(cur, job, message)
    cur.execute(f'''
        UPDATE {SCHEMA}.automation_jobs SET status = %s, step = 'done', last_error = NULL, locked_until = NULL,
               payload = payload || %s::jsonb, updated_at = NOW()
        WHERE id = %s
    ''', (status, json.dumps({'action_result': result}, ensure_ascii=False, default=str), job['id']))
    log(cur, job['id'], 'info', message, result)
    return status


TRANSACTIONS_URL = 'https://functions.poehali.dev/d977ccf7-aaab-48a4-b418-798c34bc70ec'
# Расхождение смотрит платежи не старше этого окна: старые разбираются вручную, не пробиваем историю.
DISCREPANCY_WINDOW_HOURS = 72


def enqueue_discrepancies(cur, conn, company_id) -> int:
    '''
    Сценарий «Расхождение». Вид «Оплачен, но нет чека» (по умолчанию): оплаченные платежи компании
    без чека кассы и ОФД, с оплаты которых прошло не меньше delay_minutes (и не больше окна).
    Вид «Висит в ожидании оплаты»: счета Екомкассы в статусе «ожидает оплату» - см. enqueue_pending_invoices.
    Один платёж - одно задание на сценарий.
    '''
    if not company_id:
        return 0
    cur.execute(f'''
        SELECT id, COALESCE((field_mapping->>'delay_minutes')::int, 60),
               COALESCE(field_mapping->>'discrepancy_kind', 'missing_receipt'),
               COALESCE((field_mapping->>'lookback_days')::int, 3)
        FROM {SCHEMA}.automation_scenarios
        WHERE company_id = %s AND trigger_type = 'discrepancy' AND status = 'active' AND removed_at IS NULL
    ''', (company_id,))
    rows = cur.fetchall()
    scenarios = [(sid, d) for sid, d, kind, _ in rows if kind != 'pending_invoice']
    invoice_scenarios = [(sid, d, lb) for sid, d, kind, lb in rows if kind == 'pending_invoice']
    created = 0
    if invoice_scenarios:
        try:
            created += enqueue_pending_invoices(cur, conn, company_id, invoice_scenarios)
        except Exception as e:
            conn.rollback()
            print(f'pending invoices scan failed: {e}')
    if not scenarios:
        return created
    min_delay = min(d for _, d in scenarios)
    url = (f'{TRANSACTIONS_URL}?company_id={company_id}&paged=1&missing_receipts=1'
           f'&older_than_min={min_delay}&newer_than_hours={DISCREPANCY_WINDOW_HOURS}')
    with urllib.request.urlopen(urllib.request.Request(url, headers=internal_headers()), timeout=20) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    now_utc = datetime.utcnow()
    for scenario_id, delay in scenarios:
        for p in data.get('payments') or []:
            paid_at = datetime.fromisoformat(str(p['occurred_at'])).replace(tzinfo=None) if p.get('occurred_at') else None
            if not paid_at or paid_at > now_utc - timedelta(minutes=delay):
                continue
            cur.execute(f'''
                INSERT INTO {SCHEMA}.automation_jobs (company_id, scenario_id, source_type, source_id, payload)
                VALUES (%s, %s, 'payment', %s, %s)
                ON CONFLICT (scenario_id, source_type, source_id) DO NOTHING
                RETURNING id
            ''', (company_id, scenario_id, str(p['id']),
                  json.dumps({'webhook_payment_id': p['id'], 'reason': 'discrepancy'}, ensure_ascii=False)))
            row = cur.fetchone()
            if row:
                created += 1
                log(cur, row[0], 'info',
                    f"Расхождение: платёж {p.get('title')} на {float(p.get('amount') or 0):.2f} ₽ без чека дольше {delay} мин")
    conn.commit()
    return created


# Статусы счёта Екомкассы «ожидает оплату» и пауза перед повторной проверкой неоплаченного счёта.
PENDING_INVOICE_STATUSES = {'CREATED', 'WAITING'}
INVOICE_RECHECK_HOURS = 6
INVOICE_SEARCH_PAGES = 4


def enqueue_pending_invoices(cur, conn, company_id, scenarios) -> int:
    '''
    Счета (INVC) Екомкассы, которые дольше delay_minutes висят в «ожидает оплату» (за lookback_days).
    Задание на каждый счёт; оплату проверяем в эквайринге по номеру заказа (UUID счёта) уже в задании.
    Неоплаченный счёт (задание «Пропущен») перепроверяем не чаще раза в INVOICE_RECHECK_HOURS.
    '''
    kassa = company_cash_register(cur, company_id)
    if not kassa:
        return 0
    lookback = max(1, min(max(lb for _, _, lb in scenarios), 31))
    since = (datetime.utcnow() - timedelta(days=lookback)).strftime('%Y-%m-%dT%H:%M:%SZ')
    items = []
    for page in range(INVOICE_SEARCH_PAGES):
        status, data = ecom_call(kassa, 'POST', '/api/mobile/v1/orders/search',
                                 {'since': since, 'orderTypes': ['INVC'], 'offset': page * 500, 'limit': 500})
        batch = (data or {}).get('result') if status == 200 and isinstance(data, dict) else None
        if not isinstance(batch, list):
            print(f'ecomkassa search failed: {status} {str(data)[:200]}')
            break
        items += batch
        if len(batch) < 500:
            break
    pending = [i for i in items if i.get('orderId') and str(i.get('status')) in PENDING_INVOICE_STATUSES]
    now_utc = datetime.utcnow()
    created = 0
    for scenario_id, delay, lb in scenarios:
        border = now_utc - timedelta(days=lb)
        for item in pending:
            try:
                updated = datetime.fromisoformat(str(item.get('updated')).replace('Z', '+00:00')).replace(tzinfo=None)
            except (TypeError, ValueError):
                updated = None
            if updated and (updated > now_utc - timedelta(minutes=delay) or updated < border):
                continue
            uid = str(item['orderId'])
            payload = {'reason': 'pending_invoice', 'invoice_uuid': uid, 'amount': item.get('total'),
                       'external_id': item.get('externalId'), 'updated': item.get('updated')}
            cur.execute(f'''
                SELECT id, status, updated_at < NOW() - INTERVAL '{INVOICE_RECHECK_HOURS} hours'
                FROM {SCHEMA}.automation_jobs WHERE scenario_id = %s AND payload->>'invoice_uuid' = %s
            ''', (scenario_id, uid))
            existing = cur.fetchone()
            if existing:
                if existing[1] == 'skipped' and existing[2] and existing[0]:
                    cur.execute(f'''
                        UPDATE {SCHEMA}.automation_jobs SET status = 'new', step = 'prepare', attempts = 0,
                               next_attempt_at = NOW(), last_error = NULL, updated_at = NOW()
                        WHERE id = %s AND source_type = 'ecom_invoice'
                        RETURNING id
                    ''', (existing[0],))
                    if cur.fetchone():
                        log(cur, existing[0], 'info', f'Счёт {uid} всё ещё ждёт оплату - проверяем снова')
                continue
            cur.execute(f'''
                INSERT INTO {SCHEMA}.automation_jobs (company_id, scenario_id, source_type, source_id, payload)
                VALUES (%s, %s, 'ecom_invoice', %s, %s)
                ON CONFLICT (scenario_id, source_type, source_id) DO NOTHING
                RETURNING id
            ''', (company_id, scenario_id, uid, json.dumps(payload, ensure_ascii=False)))
            row = cur.fetchone()
            if row:
                created += 1
                log(cur, row[0], 'info',
                    f"Расхождение: счёт Екомкассы {uid} на {float(item.get('total') or 0):.2f} ₽ "
                    f"висит в «ожидает оплату» - проверим оплату в эквайринге")
    conn.commit()
    return created


def run(cur, conn, company_id=None, job_id=None) -> Dict[str, int]:
    jobs = claim_jobs(cur, company_id, job_id)
    result: Dict[str, int] = {}
    active = []
    for job in jobs:
        if not job.get('was_stuck'):
            active.append(job)
            continue
        message = 'Обработка прервалась (сбой или касса не ответила)'
        if retry_delay(job['attempts'] - 1) is None and not job_id:
            # Зависало на каждой попытке - лимит исчерпан, дальше только вручную.
            mark_failed(cur, job, message, job['attempts'] - 1)
            result['failed'] = result.get('failed', 0) + 1
            continue
        log(cur, job['id'], 'error', f'{message} - задание взято в работу повторно')
        active.append(job)
    conn.commit()
    for job in active:
        status = process_job(cur, job)
        conn.commit()
        result[status] = result.get(status, 0) + 1
    if result.get('failed'):
        signal_notifications(company_id)
    return result


def signal_notifications(company_id=None, daily: bool = False):
    '''Сигнал отправщику уведомлений: разошлёт дубли в мессенджеры/почту (+ ежедневная проверка).'''
    try:
        req = urllib.request.Request(
            NOTIFICATIONS_URL,
            data=json.dumps({'action': 'dispatch', 'company_id': company_id, 'daily': daily}).encode('utf-8'),
            headers={'Content-Type': 'application/json', **internal_headers()},
            method='POST'
        )
        urllib.request.urlopen(req, timeout=3 if daily else 1.5).close()
    except Exception:
        pass


def _handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Журнал автоматизации и обработчик подготовки данных.
    GET ?company_id=[&status=][&scenario_id=][&limit=] - журнал заданий
    GET ?company_id=&job_id= - задание и его история шагов
    POST {action: "run", company_id?} - обработать задания в очереди (сигнал из
         приёма вебхука, внешний "будильник" или открытие раздела)
    POST {action: "retry", company_id, job_id} - повторить задание вручную
    '''
    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    params = event.get('queryStringParameters') or {}
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        if method == 'POST':
            body = json.loads(event.get('body') or '{}')
            action = body.get('action')
            if action == 'run':
                if body.get('company_id'):
                    try:
                        enqueue_discrepancies(cur, conn, body['company_id'])
                    except Exception as e:
                        conn.rollback()
                        print(f'discrepancy scan failed: {e}')
                processed = run(cur, conn, body.get('company_id'))
                if body.get('heartbeat') and body.get('company_id'):
                    # Сигнал из открытого кабинета: заодно - неотправленные дубли
                    # уведомлений и ежедневная проверка «платежи без чека за вчера»,
                    # только если по компании есть что делать (без лишних вызовов).
                    # «Вчера» по часовому поясу компании считаем в коде: функции поясов в SQL платформа запрещает.
                    cur.execute(f'SELECT timezone FROM {SCHEMA}.companies WHERE id = %s', (body['company_id'],))
                    tz_row = cur.fetchone()
                    try:
                        company_tz = ZoneInfo((tz_row[0] if tz_row else None) or 'Europe/Moscow')
                    except Exception:
                        company_tz = ZoneInfo('Europe/Moscow')
                    yesterday = (datetime.now(company_tz).date() - timedelta(days=1)).isoformat()
                    cur.execute(f'''
                        SELECT
                            EXISTS (SELECT 1 FROM {SCHEMA}.notification_deliveries d
                                    JOIN {SCHEMA}.notifications n ON n.id = d.notification_id
                                    WHERE n.company_id = %s AND d.status = 'pending'),
                            NOT EXISTS (SELECT 1 FROM {SCHEMA}.notification_checks c
                                        WHERE c.company_id = %s AND c.kind = 'missing_receipts' AND c.period = %s)
                    ''', (body['company_id'], body['company_id'], yesterday))
                    pending, daily_due = cur.fetchone()
                    if pending or daily_due:
                        signal_notifications(body['company_id'], daily=daily_due)
                return respond(200, {'success': True, 'processed': processed})
            if action == 'retry':
                if not body.get('company_id') or not body.get('job_id'):
                    return respond(400, {'error': 'company_id and job_id required'})
                cur.execute(f'''
                    UPDATE {SCHEMA}.automation_jobs SET next_attempt_at = NOW(), attempts = 0, status = 'new', updated_at = NOW()
                    WHERE id = %s AND company_id = %s AND status IN ('error', 'failed', 'skipped') RETURNING id
                ''', (body['job_id'], body['company_id']))
                if not cur.fetchone():
                    conn.rollback()
                    return respond(404, {'error': 'Задание не найдено или не в ошибке'})
                log(cur, body['job_id'], 'info', 'Повтор запущен вручную')
                conn.commit()
                return respond(200, {'success': True, 'processed': run(cur, conn, job_id=body['job_id'])})
            return respond(400, {'error': 'Unknown action'})

        if method != 'GET':
            return respond(405, {'error': 'Method not allowed'})

        company_id = params.get('company_id')
        if not company_id:
            return respond(400, {'error': 'company_id required'})

        if params.get('job_id'):
            cur.execute(f'''
                SELECT level, message, details, created_at FROM {SCHEMA}.automation_job_log
                WHERE job_id = %s AND job_id IN (SELECT id FROM {SCHEMA}.automation_jobs WHERE company_id = %s)
                ORDER BY created_at, id
            ''', (params['job_id'], company_id))
            history = [{'level': r[0], 'message': r[1], 'details': r[2], 'created_at': r[3]} for r in cur.fetchall()]
            cur.execute(f'SELECT prepared_data, payload FROM {SCHEMA}.automation_jobs WHERE id = %s AND company_id = %s',
                        (params['job_id'], company_id))
            row = cur.fetchone()
            return respond(200, {'success': True, 'history': history,
                                 'prepared_data': row[0] if row else None, 'payload': row[1] if row else None})

        where = ['j.company_id = %s']
        args: list = [company_id]
        if params.get('status'):
            where.append('j.status = %s')
            args.append(params['status'])
        if params.get('scenario_id'):
            where.append('j.scenario_id = %s')
            args.append(params['scenario_id'])
        limit = min(int(params.get('limit', 100)), 500)
        cur.execute(f'''
            SELECT j.id, j.scenario_id, s.name, j.source_type, j.source_id, j.status, j.step,
                   j.attempts, j.last_error, j.next_attempt_at, j.created_at, j.updated_at
            FROM {SCHEMA}.automation_jobs j
            JOIN {SCHEMA}.automation_scenarios s ON s.id = j.scenario_id
            WHERE {' AND '.join(where)}
            ORDER BY j.created_at DESC LIMIT {limit}
        ''', args)
        jobs = [{
            'id': r[0], 'scenario_id': r[1], 'scenario_name': r[2], 'source_type': r[3], 'source_id': r[4],
            'status': r[5], 'step': r[6], 'attempts': r[7], 'last_error': r[8],
            'next_attempt_at': r[9], 'created_at': r[10], 'updated_at': r[11]
        } for r in cur.fetchall()]
        cur.execute(f'''
            SELECT COUNT(*) FILTER (WHERE status = 'failed'), COUNT(*) FILTER (WHERE status = 'error')
            FROM {SCHEMA}.automation_jobs WHERE company_id = %s
        ''', (company_id,))
        failed_count, retry_count = cur.fetchone()
        return respond(200, {'success': True, 'jobs': jobs,
                             'counts': {'failed': failed_count, 'retry': retry_count}})
    finally:
        cur.close()
        conn.close()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''Точка входа: обработка запроса + итог для админки, если вызвал планировщик.'''
    denied = guard(event)
    if denied:
        return denied

    resp = _handle(event, context)
    if event.get('httpMethod', 'POST') == 'POST':
        record_cron_run(event, resp, 'automation', 'processed')
    return resp

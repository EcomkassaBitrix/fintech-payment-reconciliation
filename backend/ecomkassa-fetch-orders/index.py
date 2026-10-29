import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import psycopg2

from ecomkassa_token import ensure_valid_token
from ecomkassa_api import search_orders
from fiscal_merge import merge_after_ecomkassa
from cron_report import record_cron_run
from auth_guard import guard, subscription_guard

SCHEMA = 't_p83864310_fintech_payment_reco'
ECOMKASSA_BASE_URL = 'https://app.ecomkassa.ru'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}

ALLOWED_ORDER_TYPES = {'VCHR', 'INVC', 'CORD'}
ALLOWED_STATUSES = {'CREATED', 'PAID', 'COMPLETED', 'CANCELED', 'WAITING', 'FAILED'}

# Сколько страниц поиска (по 500 записей) просматриваем за один вызов, пока
# не наберём достаточно кандидатов для текущей пачки - защита от зависания
# функции на аномально большом периоде без реального прогресса.
MAX_SEARCH_PAGES = 20

DEFAULT_BATCH_SIZE = 8
MAX_BATCH_SIZE = 30


# Источник записей для ленты «События»: крон или ручная загрузка (ставится на каждый вызов).
ORIGIN = 'manual'


def response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
        'body': json.dumps(body, ensure_ascii=False),
        'isBase64Encoded': False
    }


def fetch_report(token: str, store_id: str, order_id: Any, protocol_version: str = 'v4',
                  timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    '''GET /fiscalorder/{version}/{storeId}/report/{orderId} - полные фискальные данные чека.'''
    import urllib.request
    import urllib.error

    url = f'{ECOMKASSA_BASE_URL}/fiscalorder/{protocol_version}/{store_id}/report/{order_id}'
    req = urllib.request.Request(url, headers={'Token': token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None


def parse_receipt_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), '%d.%m.%Y %H:%M:%S').isoformat()
    except ValueError:
        return None


def find_gateway_integration(cur, company_id: int) -> Optional[int]:
    '''
    Находит активную интеграцию "Екомкасса — платёжный шлюз" (provider slug
    ecomkassa_gateway) компании - именно её integration_id использует "живой"
    вебхук колбэка при создании записи в webhook_payments (см.
    webhook-receive/ecomkassa_gateway_handler.py). При дозагрузке синтетический
    платёж должен писаться под тем же integration_id, иначе один и тот же
    реальный платёж от live-вебхука и от дозагрузки превратится в 2 разные
    строки (уникальность в БД - по (integration_id, payment_id, status)).
    Если у компании шлюз не подключён вовсе - live-вебхук в принципе не может
    существовать, тогда безопасно используем integration_id самой кассы.
    '''
    cur.execute(f'''
        SELECT ui.id
        FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug = 'ecomkassa_gateway' AND ui.status = 'active'
        ORDER BY ui.id
        LIMIT 1
    ''', (company_id,))
    row = cur.fetchone()
    return row[0] if row else None


def notify_receipt_failed(cur, schema: str, job_id: int, message: str, data: Dict[str, Any]) -> None:
    '''
    Касса отказала в чеке сценария: уведомление в кабинет компании (одно на задание) и дубли
    в мессенджер/почту тем, кто подписан на «Касса не пробила чек» в блоке уведомлений.
    '''
    cur.execute(f'''
        INSERT INTO {schema}.notifications (company_id, kind, level, title, message, link_module, entity_type, entity_id, payload)
        SELECT j.company_id, 'receipt_failed', 'error', 'Касса не пробила чек',
               'Сценарий «' || COALESCE(s.name, '—') || '», ' ||
               CASE WHEN j.source_type = 'payment' THEN 'платёж #' || COALESCE(wp.payment_id, j.source_id)
                    WHEN j.source_type = 'crm_deal' THEN 'сделка CRM #' || j.source_id
                    WHEN j.source_type = 'crm_lead' THEN 'лид CRM #' || j.source_id
                    ELSE j.source_type || ' #' || j.source_id END ||
               '. ' || %s || '. Исправьте причину и повторите задание в журнале автоматизации.',
               'automation', 'automation_job', j.id::text,
               jsonb_build_object('job_id', j.id, 'scenario_id', j.scenario_id, 'external_id', %s::text)
        FROM {schema}.automation_jobs j
        LEFT JOIN {schema}.automation_scenarios s ON s.id = j.scenario_id
        LEFT JOIN {schema}.webhook_payments wp ON j.source_type = 'payment' AND wp.id::text = j.source_id
        WHERE j.id = %s
          AND NOT EXISTS (SELECT 1 FROM {schema}.notifications n
                          WHERE n.company_id = j.company_id AND n.kind = 'receipt_failed'
                            AND n.entity_type = 'automation_job' AND n.entity_id = j.id::text
                            AND n.created_at > NOW() - INTERVAL '1 hour')
        RETURNING id, company_id
    ''', (message, data.get('external_id'), job_id))
    row = cur.fetchone()
    if not row:
        return
    cur.execute(f'''
        INSERT INTO {schema}.notification_deliveries (notification_id, user_id, channel)
        SELECT %s, p.user_id, p.channel
        FROM {schema}.notification_preferences p
        JOIN {schema}.company_users cu ON cu.company_id = p.company_id AND cu.user_id = p.user_id AND cu.status = 'active'
        WHERE p.company_id = %s AND p.channel IS NOT NULL
        ON CONFLICT (notification_id, user_id) DO NOTHING
    ''', (row[0], row[1]))


def log_fiscal_result(cur, schema: str, doc_rows, status: str, data: Dict[str, Any], via: str) -> None:
    '''
    Строка в журнал задания сценария, когда касса окончательно пробила чек (или отказала):
    номер ФД, ФП и сумма - по уведомлению кассы или по подгрузке из Екомкассы.
    '''
    if status not in ('done', 'fail'):
        return
    payload = data.get('payload') if isinstance(data.get('payload'), dict) else {}
    if status == 'done':
        parts = []
        if payload.get('fiscal_document_number'):
            parts.append(f"ФД {payload['fiscal_document_number']}")
        if payload.get('fiscal_document_attribute'):
            parts.append(f"ФП {payload['fiscal_document_attribute']}")
        if payload.get('total') is not None:
            try:
                parts.append(f"{float(payload['total']):.2f} ₽")
            except (TypeError, ValueError):
                pass
        message = f"Чек пробит кассой{': ' + ', '.join(parts) if parts else ''} ({via})"
        level = 'info'
    else:
        err = data.get('error')
        text = err.get('text') if isinstance(err, dict) else err
        message = f"Касса не пробила чек{': ' + str(text) if text else ''} ({via})"
        level = 'error'
    details = json.dumps({'uuid': data.get('uuid'), 'external_id': data.get('external_id'),
                          'permalink': data.get('permalink'), 'payload': payload or None}, ensure_ascii=False)
    for job_id, old_status in doc_rows:
        if job_id and old_status != status:
            cur.execute(f'''
                INSERT INTO {schema}.automation_job_log (job_id, level, message, details)
                VALUES (%s, %s, %s, %s)
            ''', (job_id, level, message, details))
            if status == 'fail':
                notify_receipt_failed(cur, schema, job_id, message.rsplit(' (', 1)[0], data)


def save_receipt(cur, integration_id: int, company_id: int, order_id: Any,
                  legacy_no: Any, order_type: Optional[str], report_data: Dict[str, Any],
                  is_sale: Optional[bool] = None, is_correction: Optional[bool] = None) -> Tuple[Optional[int], Optional[float]]:
    '''
    Сохраняет фискальный чек/заказ по ответу report() в ecomkassa_receipts - тот
    же формат, что использует обработчик вебхука шлюза (см.
    webhook-receive/ecomkassa_gateway_handler.py:save_receipt_from_report), чтобы
    дозагруженные исторические документы участвовали в сверке наравне с "живыми".
    order_type (VCHR/INVC/CORD) сохраняется отдельной колонкой - от него зависит,
    как документ будет представлен в реестре транзакций (чек кассы или заказ).
    Returns: (receipt_id, total_sum)
    '''
    payload = report_data.get('payload') or {}
    total_sum = payload.get('total')
    doc_number = payload.get('fiscal_receipt_number') or payload.get('fiscal_document_number')
    doc_datetime = parse_receipt_datetime(payload.get('receipt_datetime'))

    invoice_payload = report_data.get('invoice_payload') or {}
    payment_provider = invoice_payload.get('provider') if isinstance(invoice_payload, dict) else None

    status = report_data.get('status') or 'done'

    cur.execute(f'''
        INSERT INTO {SCHEMA}.ecomkassa_receipts (
            integration_id, company_id, order_id, legacy_no, status,
            total_sum, doc_number, doc_datetime, raw_data, payment_provider, order_type,
            is_sale, is_correction, origin
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (integration_id, order_id) DO UPDATE SET
            is_sale = COALESCE(EXCLUDED.is_sale, {SCHEMA}.ecomkassa_receipts.is_sale),
            is_correction = COALESCE(EXCLUDED.is_correction, {SCHEMA}.ecomkassa_receipts.is_correction),
            status = EXCLUDED.status,
            total_sum = COALESCE(EXCLUDED.total_sum, {SCHEMA}.ecomkassa_receipts.total_sum),
            doc_number = COALESCE(EXCLUDED.doc_number, {SCHEMA}.ecomkassa_receipts.doc_number),
            doc_datetime = COALESCE(EXCLUDED.doc_datetime, {SCHEMA}.ecomkassa_receipts.doc_datetime),
            raw_data = EXCLUDED.raw_data,
            payment_provider = COALESCE(EXCLUDED.payment_provider, {SCHEMA}.ecomkassa_receipts.payment_provider),
            order_type = COALESCE(EXCLUDED.order_type, {SCHEMA}.ecomkassa_receipts.order_type)
        RETURNING id
    ''', (
        integration_id, company_id, str(order_id), str(legacy_no) if legacy_no else str(order_id),
        status, total_sum, str(doc_number) if doc_number else None, doc_datetime,
        json.dumps(report_data), payment_provider, order_type, is_sale, is_correction, ORIGIN
    ))
    result = cur.fetchone()
    receipt_id = result[0] if result else None
    merge_after_ecomkassa(cur, receipt_id)
    if receipt_id:
        # Документ отправлен нашим сценарием (чек, коррекция, заказ) - довязываем его к платежу
        # по UUID кассы или нашему номеру документа, даже если уведомление кассы не пришло.
        doc_external_id = str(report_data.get('external_id') or legacy_no or order_id)
        cur.execute(f'''
            SELECT job_id, status FROM {SCHEMA}.automation_documents
            WHERE kassa_integration_id = %s AND (ecom_uuid = %s OR external_id = %s)
        ''', (integration_id, str(order_id), doc_external_id))
        before = cur.fetchall()
        cur.execute(f'''
            UPDATE {SCHEMA}.automation_documents
            SET ecom_uuid = COALESCE(ecom_uuid, %s), receipt_id = %s, status = %s, updated_at = NOW()
            WHERE kassa_integration_id = %s AND (ecom_uuid = %s OR external_id = %s)
        ''', (str(order_id), receipt_id, status, integration_id, str(order_id), doc_external_id))
        log_fiscal_result(cur, SCHEMA, before, status, {**report_data, 'uuid': report_data.get('uuid') or str(order_id)},
                          'найден подгрузкой из Екомкассы')
    return receipt_id, float(total_sum) if total_sum else None


PAID_ORDER_STATUSES = {'PAID', 'COMPLETED'}
# Счёт «ожидает оплату»: храним отдельно (ecomkassa_pending_invoices) - это не платёж,
# в транзакции он не попадает, report()/корзину/чек по нему не запрашиваем.
PENDING_INVOICE_STATUSES = {'CREATED', 'WAITING'}


def is_pending_invoice(item: Dict[str, Any]) -> bool:
    return item.get('orderType') == 'INVC' and item.get('status') in PENDING_INVOICE_STATUSES


def save_pending_invoice(cur, integration_id: int, company_id: int, item: Dict[str, Any]) -> bool:
    '''Счёт «ожидает оплату» - только для сценария «Висит в ожидании оплаты». Returns: новый ли.'''
    uid = str(item.get('orderId') or '')
    if not uid:
        return False
    try:
        updated = datetime.fromisoformat(str(item.get('updated')).replace('Z', '+00:00'))
        updated = updated.astimezone(timezone.utc).replace(tzinfo=None) if updated.tzinfo else updated
    except (TypeError, ValueError):
        updated = None
    try:
        amount = float(item.get('total')) if item.get('total') is not None else None
    except (TypeError, ValueError):
        amount = None
    cur.execute(f'''
        INSERT INTO {SCHEMA}.ecomkassa_pending_invoices
            (company_id, integration_id, invoice_uuid, external_id, status, amount, invoice_updated_at, raw_data, origin)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (integration_id, invoice_uuid) DO UPDATE SET
            status = EXCLUDED.status, amount = EXCLUDED.amount, invoice_updated_at = EXCLUDED.invoice_updated_at,
            raw_data = EXCLUDED.raw_data, external_id = EXCLUDED.external_id, updated_at = NOW()
        RETURNING (xmax = 0)
    ''', (company_id, integration_id, uid, (str(item.get('externalId'))[:255] if item.get('externalId') else None),
          str(item.get('status')), amount, updated, json.dumps(item, ensure_ascii=False, default=str), ORIGIN))
    row = cur.fetchone()
    return bool(row and row[0])


def drop_pending_invoice(cur, company_id: int, order_id: Any) -> None:
    '''Счёт оплачен/пробит - из «ожидает оплату» убираем.'''
    if order_id:
        cur.execute(f'DELETE FROM {SCHEMA}.ecomkassa_pending_invoices WHERE company_id = %s AND invoice_uuid = %s',
                    (company_id, str(order_id)))


def is_invoice_paid(item: Dict[str, Any], report_data: Dict[str, Any]) -> bool:
    '''Счёт (INVC) оплачен покупателем: статус документа PAID или COMPLETED.'''
    if item.get('orderType') != 'INVC' or item.get('status') not in PAID_ORDER_STATUSES:
        return False
    invoice_payload = report_data.get('invoice_payload')
    return isinstance(invoice_payload, dict) and bool(invoice_payload.get('provider'))


def invoice_amount(item: Dict[str, Any], report_data: Dict[str, Any]) -> Optional[float]:
    invoice_payload = report_data.get('invoice_payload') or {}
    for value in ((report_data.get('payload') or {}).get('total'), invoice_payload.get('amount'),
                  invoice_payload.get('total'), item.get('total')):
        try:
            if value is not None and float(value) > 0:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def save_synthetic_payment(cur, gateway_integration_id: int, company_id: int, order_id: Any,
                            receipt_id: Optional[int], total_sum: Optional[float], report_data: Dict[str, Any]) -> None:
    '''
    Счета (INVC) и часть заказов (CORD), оплаченные через прокси-шлюз Екомкассы,
    в report() содержат invoice_payload с полем "provider" (напр. TOCHKA_SBP) -
    это и есть сам факт платежа через конкретную платёжную систему. "Живой"
    вебхук шлюза создаёт для него отдельную строку в webhook_payments сразу в
    момент оплаты - при дозагрузке событие вебхука уже потеряно, поэтому
    синтезируем ту же запись здесь по данным report(), с receipt_id проставленным
    напрямую (та же связь, что использует live-путь), чтобы платёж сразу был
    виден в реестре транзакций и группировался с чеком.
    Вызывающий код уже гарантировал, что счёт оплачен (is_invoice_paid), поэтому
    статус платежа = CONFIRMED. receipt_id может быть пустым, если чек ещё не done -
    он проставится при следующей загрузке.
    '''
    invoice_payload = report_data.get('invoice_payload') or {}
    if not isinstance(invoice_payload, dict):
        return
    payment_provider = invoice_payload.get('provider')
    if not payment_provider:
        return

    uid = str(order_id)
    cur.execute(f'''
        INSERT INTO {SCHEMA}.webhook_payments (
            integration_id, company_id, payment_id, terminal_key,
            amount, order_id, status, payment_status, error_code,
            customer_email, customer_phone, pan, card_type, exp_date,
            raw_data, receipt_id, payment_provider, origin
        ) VALUES (%s, %s, %s, NULL, %s, %s, 'CONFIRMED', NULL, NULL, NULL, NULL, NULL, NULL, NULL, %s, %s, %s, %s)
        ON CONFLICT (integration_id, payment_id, status) DO UPDATE SET
            receipt_id = COALESCE(EXCLUDED.receipt_id, {SCHEMA}.webhook_payments.receipt_id),
            raw_data = CASE WHEN EXCLUDED.receipt_id IS NOT NULL THEN EXCLUDED.raw_data
                            ELSE {SCHEMA}.webhook_payments.raw_data END,
            payment_provider = COALESCE(EXCLUDED.payment_provider, {SCHEMA}.webhook_payments.payment_provider),
            amount = CASE WHEN {SCHEMA}.webhook_payments.amount = 0
                          THEN EXCLUDED.amount
                          ELSE {SCHEMA}.webhook_payments.amount END
    ''', (
        gateway_integration_id, company_id, uid,
        total_sum or 0, uid,
        json.dumps(report_data), receipt_id, payment_provider, ORIGIN
    ))


def collect_candidates(token: str, since: Optional[str], until: Optional[str],
                        order_types: List[str], statuses: List[str],
                        need_count: int, type_statuses: Optional[Dict[str, List[str]]] = None) -> tuple:
    '''
    Проходит страницы /orders/search (по 500 записей), фильтрует локально по
    статусу (API фильтрует только по типу документа и дате) и копит подходящих
    кандидатов, пока их не наберётся хотя бы need_count или не кончатся
    страницы/не будет достигнут защитный лимит MAX_SEARCH_PAGES.
    Returns: (candidates: list, matched_total_so_far: int, capped: bool, error: str|None)
    '''
    candidates = []
    offset = 0
    page = 0
    capped = False

    while page < MAX_SEARCH_PAGES:
        page += 1
        result = search_orders(token, since=since, until=until, order_types=order_types, offset=offset)

        if result is None:
            return candidates, len(candidates), capped, 'Екомкасса не ответила на запрос'
        if result.get('error'):
            return candidates, len(candidates), capped, result.get('error', 'Ошибка запроса к Екомкассе')

        page_items = result.get('result', [])
        if not page_items:
            break

        for item in page_items:
            allowed = (type_statuses or {}).get(item.get('orderType')) or statuses
            if item.get('status') in allowed:
                candidates.append(item)

        if len(page_items) < 500:
            break

        offset += 500

        if len(candidates) >= need_count and page >= 2:
            # Уже нашли достаточно для текущей пачки и просмотрели больше одной
            # страницы - можно не листать до конца ради точного matched_total,
            # это лишь ускоряет типичный случай (пачка находится на первых страницах).
            break

    if page >= MAX_SEARCH_PAGES:
        capped = True

    return candidates, len(candidates), capped, None


def _handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Дозагрузка исторических чеков/счетов/заказов Екомкассы за период вручную
    (для случаев, когда часть данных не попала через вебхук - например,
    интеграцию подключили уже после того, как в кассе накопились платежи).
    Работает в 2 шага:
    1) POST /api/mobile/v1/orders/search - находит документы за период
       [date_from, date_to] с фильтром по типу (VCHR - чеки, INVC - счета,
       CORD - курьерские заказы), листая страницы по 500 записей; статус
       (CREATED/PAID/COMPLETED/CANCELED/WAITING/FAILED) фильтруется локально,
       т.к. API его не поддерживает.
    2) Для найденных кандидатов (пачками, см. offset/batch_size) параллельно
       вызывает GET .../report/{orderId} за полными фискальными данными и
       сохраняет в ecomkassa_receipts вместе с order_type - в том же формате,
       что и обычные вебхуки, поэтому дозагруженные документы сразу участвуют
       в сверке и матчинге с платежами.
    Если report() содержит invoice_payload (счёт/заказ оплачен через
    прокси-шлюз Екомкассы конкретной платёжной системой, напр. TOCHKA_SBP) -
    дополнительно синтезируется запись платежа в webhook_payments с сразу
    проставленным receipt_id, т.к. "живого" вебхука этого события уже не
    было/не будет - см. save_synthetic_payment().
    Пагинация по кандидатам нужна, т.к. report() на каждый документ - это
    отдельный сетевой запрос, и сотни таких запросов не укладываются в таймаут
    одного вызова функции - фронтенд вызывает повторно с новым offset, пока
    done=false.
    Args: company_id (обязателен), date_from, date_to (ISO, обязательны),
    order_types (['VCHR','INVC','CORD'], default ['VCHR']),
    statuses (default ['COMPLETED']), type_statuses ({'INVC': ['PAID', ...]} - статусы
    отдельно по типу документа, перекрывают statuses), offset (default 0), batch_size (default 8, max 30)
    Returns: matched_total, processed, inserted, skipped, next_offset, done, capped
    '''

    method = event.get('httpMethod', 'POST')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    if method != 'POST':
        return response(405, {'error': 'Method not allowed'})

    body = json.loads(event.get('body', '{}') or '{}')
    global ORIGIN
    ORIGIN = 'cron' if body.get('cron_tick') else 'manual'
    company_id = body.get('company_id')
    date_from = body.get('date_from')
    date_to = body.get('date_to')
    order_types = body.get('order_types') or ['VCHR']
    statuses = body.get('statuses') or ['COMPLETED']
    offset = max(0, int(body.get('offset', 0)))
    batch_size = min(MAX_BATCH_SIZE, max(1, int(body.get('batch_size', DEFAULT_BATCH_SIZE))))
    # Авто-режим планировщика: окно «последние N часов», только ещё не загруженные документы.
    auto_hours = body.get('auto_hours')
    only_new = bool(body.get('only_new')) or bool(auto_hours)
    if auto_hours:
        now = datetime.utcnow()
        date_from = (now - timedelta(hours=min(72, max(1, int(auto_hours))))).isoformat()
        date_to = (now + timedelta(minutes=5)).isoformat()

    if not company_id:
        return response(400, {'error': 'company_id required'})
    if not date_from or not date_to:
        return response(400, {'error': 'date_from and date_to required'})

    order_types = [t for t in order_types if t in ALLOWED_ORDER_TYPES] or ['VCHR']
    statuses = [s for s in statuses if s in ALLOWED_STATUSES] or ['COMPLETED']
    raw_type_statuses = body.get('type_statuses') if isinstance(body.get('type_statuses'), dict) else {}
    type_statuses = {t: [s for s in (v or []) if s in ALLOWED_STATUSES]
                     for t, v in raw_type_statuses.items() if t in ALLOWED_ORDER_TYPES}
    type_statuses = {t: v for t, v in type_statuses.items() if v}

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute(f'''
            SELECT ui.id, ui.config
            FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            WHERE ui.company_id = %s AND p.slug = 'ecomkassa' AND ui.status = 'active'
            ORDER BY ui.id
            LIMIT 1
        ''', (company_id,))
        row = cur.fetchone()

        if not row:
            return response(404, {'error': 'Активная касса Екомкасса не найдена у компании'})

        integration_id, config = row
        config = json.loads(config) if isinstance(config, str) else (config or {})

        token = ensure_valid_token(cur, integration_id, config)
        store_id = config.get('store_id')
        protocol_version = config.get('protocol_version', 'v4')

        if not token or not store_id:
            return response(400, {'error': 'Касса Екомкасса не авторизована (нет токена или store_id)'})

        # Ищем один раз на весь вызов, а не на каждый документ - используется
        # только если найдутся счета/заказы с invoice_payload (см. save_synthetic_payment).
        gateway_integration_id = find_gateway_integration(cur, company_id)

        try:
            since = datetime.fromisoformat(date_from.replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%S.000Z')
            until = datetime.fromisoformat(date_to.replace('Z', '+00:00')).strftime('%Y-%m-%dT%H:%M:%S.999Z')
        except ValueError:
            return response(400, {'error': 'Некорректный формат date_from/date_to'})

        candidates, matched_total, capped, error = collect_candidates(
            token, since, until, order_types, statuses, need_count=offset + batch_size,
            type_statuses=type_statuses
        )

        if error:
            return response(200, {'success': False, 'error': error})

        if only_new and candidates:
            # Уже загруженные (чек пробит) не перезапрашиваем - иначе каждый тик
            # планировщика заново тянул бы report() по всем документам окна.
            ids = [str(c.get('orderId')) for c in candidates]
            cur.execute(f'''
                SELECT r.order_id FROM {SCHEMA}.ecomkassa_receipts r
                WHERE r.integration_id = %s AND r.status = 'done' AND r.order_id = ANY(%s)
                  AND (r.payment_provider IS NULL OR EXISTS (
                      SELECT 1 FROM {SCHEMA}.webhook_payments wp
                      WHERE wp.company_id = r.company_id AND wp.payment_id = r.order_id
                  ))
            ''', (integration_id, ids))
            known = {r[0] for r in cur.fetchall()}
            candidates = [c for c in candidates if str(c.get('orderId')) not in known]
            matched_total = len(candidates)

        batch = candidates[offset:offset + batch_size]

        inserted = 0
        skipped = 0
        payments_saved = 0

        pending_batch = [i for i in batch if is_pending_invoice(i)]
        for item in pending_batch:
            if save_pending_invoice(cur, integration_id, company_id, item):
                inserted += 1
        pending_ids = {id(i) for i in pending_batch}
        report_batch = [i for i in batch if id(i) not in pending_ids]

        # report() для счетов (INVC) у Екомкассы заметно медленнее, чем для
        # чеков (VCHR) - при последовательных запросах пачка из batch_size
        # документов легко превышала таймаут функции, и фронтенд получал 504
        # посреди дозагрузки счетов, тогда как чеки (более быстрые) успевали
        # обработаться. Запрашиваем report() параллельно - это сетевой I/O,
        # GIL не мешает, а сама БД-запись (save_receipt) остаётся
        # последовательной, т.к. курсор psycopg2 не потокобезопасен.
        with ThreadPoolExecutor(max_workers=min(8, len(report_batch)) or 1) as pool:
            reports = list(pool.map(
                lambda item: fetch_report(token, store_id, item.get('orderId'), protocol_version),
                report_batch
            ))

        for item, report_data in zip(report_batch, reports):
            order_id = item.get('orderId')
            external_id = item.get('externalId')
            order_type = item.get('orderType')

            if not report_data:
                skipped += 1
                continue

            receipt_id, total_sum = None, None
            if report_data.get('status') == 'done':
                receipt_id, total_sum = save_receipt(
                    cur, integration_id, company_id, order_id, external_id, order_type, report_data,
                    item.get('isSale'), item.get('isCorrection')
                )
                if receipt_id:
                    inserted += 1

            # Оплаченный счёт (INVC) загружаем как платёж сразу, даже если касса ещё
            # не пробила чек - чек привяжется следующим тиком, когда станет done.
            invoice_paid = is_invoice_paid(item, report_data)
            if invoice_paid or receipt_id:
                drop_pending_invoice(cur, company_id, order_id)
            if invoice_paid or (receipt_id and report_data.get('invoice_payload')):
                if total_sum is None:
                    total_sum = invoice_amount(item, report_data)
                gw_id = gateway_integration_id or integration_id
                save_synthetic_payment(cur, gw_id, company_id, order_id, receipt_id, total_sum, report_data)
                payments_saved += 1

            if not receipt_id and not invoice_paid:
                skipped += 1

        # Время синхронизации кассы - для плашки «Синхронизация: N назад».
        cur.execute(f'UPDATE {SCHEMA}.user_integrations SET last_synced_at = NOW() WHERE id = %s', (integration_id,))
        conn.commit()

        next_offset = offset + len(batch)
        done = len(batch) < batch_size or next_offset >= matched_total

        return response(200, {
            'success': True,
            'matched_total': matched_total,
            'payments_saved': payments_saved,
            'processed': len(batch),
            'inserted': inserted,
            'skipped': skipped,
            'next_offset': next_offset if not done else None,
            'done': done,
            'capped': capped
        })

    except Exception as e:
        conn.rollback()
        return response(500, {'error': str(e)})
    finally:
        cur.close()
        conn.close()



def _is_db_overload(text: str) -> bool:
    return 'rate limit' in (text or '').lower()


def _handle_with_retry(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''Перегрузка базы («rate limit exceeded») - временный сбой: ждём и повторяем, до 3 попыток.'''
    import time
    resp: Dict[str, Any] = {}
    for attempt in range(3):
        try:
            resp = _handle(event, context)
        except Exception as e:
            if not _is_db_overload(str(e)) or attempt == 2:
                raise
            time.sleep(0.7 * (attempt + 1))
            continue
        if resp.get('statusCode', 200) >= 500 and _is_db_overload(str(resp.get('body'))) and attempt < 2:
            time.sleep(0.7 * (attempt + 1))
            continue
        return resp
    return resp


def _db_retry(fn, event: Dict[str, Any]):
    '''Проверка доступа ходит в базу; при её перегрузке («rate limit») ждём и пробуем ещё раз, до 3 попыток.'''
    import time
    for attempt in range(3):
        try:
            return fn(event)
        except Exception as e:
            if attempt == 2 or 'rate limit' not in str(e).lower():
                raise
            time.sleep(0.4 * (attempt + 1))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''Точка входа: обработка запроса + итог для админки, если вызвал планировщик.'''
    denied = _db_retry(guard, event)
    if denied:
        return denied
    blocked = _db_retry(subscription_guard, event)
    if blocked:
        return blocked

    resp = _handle_with_retry(event, context)
    if event.get('httpMethod', 'POST') == 'POST':
        record_cron_run(event, resp, 'ecomkassa', 'inserted')
    return resp
import json
import os
import time

import psycopg2
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

from grouping import group_transactions, node_key, matches_filters, latest_time, local_date
from auth_guard import guard

SCHEMA = 't_p83864310_fintech_payment_reco'
DEFAULT_TZ = 'Europe/Moscow'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}


def json_ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': 200,
        'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
        'body': json.dumps(payload),
        'isBase64Encoded': False
    }


def to_json_value(val):
    if isinstance(val, Decimal):
        return float(val)
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return val


def wants(type_filter, t):
    '''type=receipt - алиас "любой чек/заказ", остальные значения - точное совпадение.'''
    if not type_filter:
        return True
    if type_filter == t:
        return True
    if type_filter == 'receipt' and t in ('receipt_ofd', 'receipt_kassa', 'receipt_order'):
        return True
    return False


def classify_receipt_sign(operation_type: Optional[str]) -> int:
    '''
    Знак вклада фискального документа в выручку по его типу операции (54-ФЗ):
    Income/приход - продажа, +; Refund Income/возврат прихода - деньги отданы
    обратно клиенту, -; Expense/расход - вы платите (напр. приём у физлица), -;
    Refund Expense/возврат расхода - деньги вернулись вам, +. Неизвестный тип,
    который явно начинается с "возврат"/"refund" - считаем отрицательным на
    всякий случай, иначе по умолчанию считаем приходом (+).
    '''
    if not operation_type:
        return 1
    t = operation_type.strip().lower()
    is_refund = 'возврат' in t or 'refund' in t or 'return' in t
    is_expense = 'расход' in t or 'expense' in t
    if is_refund and is_expense:
        return 1
    if is_refund:
        return -1
    if is_expense:
        return -1
    return 1


def receipt_kind_title(title: Optional[str]) -> Optional[str]:
    '''
    «KIND|<тип операции>|<коррекция 0/1>|<номер>» -> «Чек прихода №1», «Чек коррекции прихода №2»,
    «Чек возврата прихода №3», «Чек расхода №4». Тип - из ОФД (OperationType) или Екомкассы (isSale).
    '''
    if not title or not title.startswith('KIND|'):
        return title
    _, op, corr, number = (title.split('|', 3) + ['', '', ''])[:4]
    o = (op or '').strip().lower().replace('_', ' ')
    if o in ('refund income', 'incomereturn', 'income return', 'sell refund', 'возврат прихода'):
        kind = 'возврата прихода'
    elif o in ('refund expense', 'expensereturn', 'expense return', 'buy refund', 'возврат расхода'):
        kind = 'возврата расхода'
    elif o in ('expense', 'buy', 'расход'):
        kind = 'расхода'
    else:
        kind = 'прихода'
    return f"Чек {'коррекции ' if corr == '1' else ''}{kind} №{number}"


REFUND_STATUSES = ('REFUNDED', 'CANCELED')


def compute_signed_amount(row: Dict[str, Any]) -> float:
    '''
    Сумма транзакции с учётом знака - именно она используется в суммах для
    сверки (в отличие от row['amount'], который всегда хранит абсолютную
    величину документа как есть).
    - payment: платёж вносит вклад только пока он реально "жив" деньгами -
      AUTHORIZED/CONFIRMED (последний статус группы вебхуков) = +amount;
      REFUNDED - деньги пришли и ушли обратно, чистый эффект 0; CANCELED/
      REJECTED - деньги вообще не двигались, тоже 0.
    - receipt_ofd: знак по operation_type самого документа (54-ФЗ).
    - receipt_kassa/receipt_order: касса не хранит тип операции - берём знак
      из связанного чека ОФД, если пара найдена по фискальным реквизитам;
      без пары считаем продажей (+), как и есть по умолчанию сейчас.
    - money: банковская выписка уже отфильтрована по ключевым словам
      назначения платежа на этапе синхронизации (это все "наши" операции
      терминала/счёта) - direction='in' значит деньги пришли (+), 'out' -
      ушли, например возврат клиенту (-).
    '''
    amount = float(row.get('amount') or 0)
    t = row['type']

    if t == 'money':
        return amount if row.get('status') == 'in' else -amount

    # Сделка CRM - не движение денег, а основание: в суммы сверки не входит.
    if t == 'crm_deal':
        return 0.0

    if t == 'receipt_ofd':
        return amount * classify_receipt_sign(row.get('status'))

    if t in ('receipt_kassa', 'receipt_order'):
        linked_status = row.get('linked_ofd_status')
        return amount * classify_receipt_sign(linked_status)

    if t == 'payment':
        status = row.get('status')
        if row.get('payment_operation') == 'refund':
            # Отмена/возврат - отдельная операция группы: деньги вернулись покупателю.
            return -amount
        if status in ('AUTHORIZED', 'CONFIRMED'):
            return amount
        return 0.0

    return amount


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Точка входа: при временной перегрузке базы («rate limit exceeded», обрыв соединения)
    запрос повторяется с короткой паузой - при открытии страницы кабинет шлёт много
    запросов разом, и единичный отказ базы не должен превращаться в ошибку на экране.
    '''
    resp = None
    for attempt in range(3):
        try:
            resp = _handle(event, context)
        except psycopg2.OperationalError as e:
            print(f'[transactions-list] db connect failed (attempt {attempt + 1}): {e}')
            if attempt == 2:
                raise
            time.sleep(0.4 * (attempt + 1))
            continue
        if resp.get('statusCode') != 500:
            return resp
        error = str(json.loads(resp.get('body') or '{}').get('error') or '')
        print(f'[transactions-list] error (attempt {attempt + 1}): {error[:300]}')
        transient = any(k in error.lower() for k in ('rate limit', 'connection', 'server closed', 'timeout', 'canceling statement'))
        if not transient or attempt == 2:
            return resp
        time.sleep(0.4 * (attempt + 1))
    return resp


def _handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Единый реестр готовых для сверки транзакций: объединяет уже насыщенные
    данные из платежей (webhook_payments), чеков и заказов кассы
    (ecomkassa_receipts), чеков ОФД (ofd_receipts) и операций по расчётному
    счёту (bank_statement_transactions) в один список.

    Типы транзакций (поле type): payment, receipt_ofd, receipt_kassa,
    receipt_order, money.
    - receipt_kassa/receipt_order - обе строки из ecomkassa_receipts,
      разведены по order_type документа Екомкассы: VCHR/INVC (чек/счёт) ->
      receipt_kassa, CORD (курьерский заказ) -> receipt_order - у заказа
      деньги обычно передаются курьеру физически, это стоит явно отличать
      от кассового/интернет-чека в реестре и в сверке.
    - чеки кассы (receipt_kassa/receipt_order) и ОФД разведены на два разных
      типа намеренно: это два разных физических источника данных об одном и
      том же чеке (касса пробивает и пересылает результат сама, ОФД получает
      копию от налоговой), и их нужно сверять МЕЖДУ СОБОЙ - если касса
      случайно пробила чек дважды, в чеках кассы будет 2 записи, а в ОФД
      может быть только 1 подтверждённая - без разделения типов такую
      аномалию не увидеть.

    Платёж - особый случай: один и тот же платёж (payment_id/order_id) обычно
    прилетает НЕСКОЛЬКИМИ вебхуками по мере смены статуса (AUTHORIZED ->
    CONFIRMED -> REFUNDED и т.п.), и в БД это разные строки webhook_payments.
    Чтобы не показывать один платёж как N разных "транзакций без пары",
    все вебхуки одного payment_id/order_id схлопываются в ОДНУ транзакцию
    с последним статусом и полем webhook_history (список всех промежуточных
    статусов) - платёж считается связанным, если связь нашлась хотя бы у
    одного из вебхуков в группе.
    Платежи, оплаченные через прокси-шлюз Екомкассы (invoice_payload с полем
    provider - конкретная платёжная система вроде TOCHKA_SBP), при дозагрузке
    исторических данных синтезируются напрямую из report() чека/заказа (см.
    ecomkassa-fetch-orders/save_synthetic_payment) - "живого" вебхука такого
    события к моменту дозагрузки уже нет.

    УЧЁТ ВОЗВРАТОВ: количество транзакций (count) считается по числу
    документов как есть, без вычетов. А суммы (amount в totals_by_type и
    поле signed_amount у каждой строки) - НЕТТО с учётом знака операции:
    возврат вычитается из суммы, а не увеличивает её. Подробности знака
    смотри в compute_signed_amount().

    Связывание (linked_type/linked_source/linked_id/match_method):
    - платёж -> чек/заказ кассы: webhook_payments.receipt_id, а если его нет -
      совпадение order_id/payment_id с order_id/legacy_no/external_id/uuid
      документа кассы (linked_type зависит от order_type найденного документа -
      receipt_kassa или receipt_order).
    - чек/заказ кассы <-> чек ОФД: по триплету фискальных реквизитов
      ФН+ФД+ФПД - однозначно идентифицирует физический фискальный документ
      независимо от того, каким API он был получен.
    - деньги на р/с -> платёж: в общем случае банковская выписка не содержит
      номер заказа, но в двух конкретных случаях назначение платежа несёт
      достаточно специфичный идентификатор, чтобы связывать безопасно:
      (1) СБП-платежи через шлюз Екомкассы - банк пишет "QR ID <код>" (и в
      самой операции зачисления, и в списанной следом комиссии за перевод),
      тот же код есть в хвосте invoice_payload.link платежа ("https://web.
      qr.nspk.ru/<код>"); (2) эквайринг с явным external_id - банк пишет
      "Платеж <external_id>", тот же external_id Екомкасса передавала при
      создании платежа и он сохранён в raw_data.external_id. Оба кода
      достаточно длинные и специфичные, случайное совпадение практически
      исключено - в отличие от сопоставления по одной лишь сумме/дате.
    УДАЛЁННЫЕ (removed_at) транзакции полностью исключены из всех 5 запросов
    и из LATERAL-подзапросов связывания - "мягко удалённая" запись не
    участвует ни в списке, ни как чужая пара для связывания.

    РУЧНЫЕ СВЯЗИ (manual_transaction_links, кнопка "Связать" в реестре):
    каждой строке проставляется manual_group_id, если она входит в группу,
    связанную пользователем вручную - фронтенд объединяет такие записи в
    одну группу наравне с автоматическими (linked_id), см.
    transactionGrouping.ts.
    Args: company_id (обязателен), type (payment/receipt_ofd/receipt_kassa/
    receipt_order/money/receipt-алиас на все 3 вида чеков, опционально),
    limit, offset (опционально).
    Постраничный режим реестра (paged=1): date_from/date_to (YYYY-MM-DD, по
    часовому поясу компании), search, unmatched_only=1, types (через запятую,
    например receipt_kassa,receipt_ofd - только эти виды записей); offset/limit - в
    группах/строках, totals_by_type - по ВСЕМ отфильтрованным записям,
    context_transactions - остальные участники групп страницы (для окна
    деталей), has_more/next_offset - для автоподгрузки.
    Returns: transactions[] с полями type, source, id, occurred_at, amount,
    signed_amount, status, title, subtitle, integration_name, reference,
    raw_data, linked_type, linked_source, linked_id, match_method,
    manual_group_id, webhook_history (только для payment с несколькими
    вебхуками).
    totals_by_type[].amount - это сумма signed_amount (нетто, с учётом
    возвратов), totals_by_type[].count - число документов без вычетов.
    '''
    denied = guard(event)
    if denied:
        return denied


    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    if method != 'GET':
        return {
            'statusCode': 405,
            'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    params = event.get('queryStringParameters', {}) or {}
    company_id = params.get('company_id')
    type_filter = params.get('type')
    limit = int(params.get('limit', 100))
    offset = int(params.get('offset', 0))
    paged = params.get('paged') == '1'
    date_from = params.get('date_from') or None
    date_to = params.get('date_to') or None
    search = params.get('search') or ''
    unmatched_only = params.get('unmatched_only') == '1'
    types_filter = {t for t in (params.get('types') or '').split(',') if t}

    if not company_id:
        return {
            'statusCode': 400,
            'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'company_id required'}),
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        parts = []

        if wants(type_filter, 'payment'):
            parts.append(f'''
                SELECT
                    'payment' AS type,
                    p.slug AS source,
                    wp.id AS id,
                    COALESCE(rid_ekr.doc_datetime, km.doc_datetime, wp.created_at) AS occurred_at,
                    NULL::date AS settlement_date,
                    wp.amount AS amount,
                    wp.status AS status,
                    ('Платёж #' || wp.payment_id) AS title,
                    COALESCE(wp.payment_provider, p.name) AS subtitle,
                    ui.integration_name AS integration_name,
                    wp.order_id AS reference,
                    wp.raw_data AS raw_data,
                    CASE
                        WHEN wp.receipt_id IS NOT NULL OR km.id IS NOT NULL THEN
                            CASE WHEN COALESCE(km.order_type, rid_ekr.order_type) = 'CORD' THEN 'receipt_order' ELSE 'receipt_kassa' END
                    END AS linked_type,
                    CASE WHEN COALESCE(wp.receipt_id, km.id) IS NOT NULL THEN 'ecomkassa' END AS linked_source,
                    COALESCE(wp.receipt_id, km.id) AS linked_id,
                    CASE
                        WHEN wp.receipt_id IS NOT NULL THEN 'receipt_id'
                        WHEN km.id IS NOT NULL THEN 'order_id'
                    END AS match_method,
                    COALESCE(wp.order_id, wp.payment_id) AS group_key,
                    NULL::text AS linked_ofd_status
                FROM {SCHEMA}.webhook_payments wp
                JOIN {SCHEMA}.user_integrations ui ON ui.id = wp.integration_id
                JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
                LEFT JOIN {SCHEMA}.ecomkassa_receipts rid_ekr ON rid_ekr.id = wp.receipt_id AND rid_ekr.removed_at IS NULL
                LEFT JOIN LATERAL (
                    SELECT ekr.id, ekr.order_type, ekr.doc_datetime
                    FROM {SCHEMA}.ecomkassa_receipts ekr
                    WHERE ekr.company_id = wp.company_id
                      AND ekr.removed_at IS NULL
                      AND wp.receipt_id IS NULL
                      AND (
                        ekr.order_id = wp.order_id OR ekr.order_id = wp.payment_id OR
                        ekr.legacy_no = wp.order_id OR ekr.legacy_no = wp.payment_id OR
                        ekr.raw_data->>'external_id' = wp.order_id OR
                        ekr.raw_data->>'external_id' = wp.payment_id OR
                        ekr.raw_data->>'uuid' = wp.order_id OR
                        ekr.raw_data->>'uuid' = wp.payment_id
                      )
                    LIMIT 1
                ) km ON true
                WHERE wp.company_id = %(company_id)s AND ui.status NOT IN ('deleted', 'hidden') AND wp.removed_at IS NULL
            ''')

        if wants(type_filter, 'receipt_ofd'):
            parts.append(f'''
                SELECT
                    'receipt_ofd' AS type,
                    'ofd' AS source,
                    ofd.id AS id,
                    ofd.doc_datetime AS occurred_at,
                    NULL::date AS settlement_date,
                    ofd.total_sum AS amount,
                    ofd.operation_type AS status,
                    ('KIND|' || COALESCE(ofd.operation_type, '') || '|' ||
                        CASE WHEN (ofd.raw_data->>'IsCorrection') = 'true' THEN '1' ELSE '0' END || '|' ||
                        COALESCE(ofd.doc_number, ofd.receipt_id)) AS title,
                    'ОФД' AS subtitle,
                    ui.integration_name AS integration_name,
                    ofd.receipt_id AS reference,
                    ofd.raw_data AS raw_data,
                    CASE WHEN km.id IS NOT NULL THEN 'receipt_kassa' END AS linked_type,
                    CASE WHEN km.id IS NOT NULL THEN 'ecomkassa' END AS linked_source,
                    km.id AS linked_id,
                    CASE WHEN km.id IS NOT NULL THEN 'fiscal_triplet' END AS match_method,
                    NULL::text AS group_key,
                    NULL::text AS linked_ofd_status
                FROM {SCHEMA}.ofd_receipts ofd
                JOIN {SCHEMA}.user_integrations ui ON ui.id = ofd.integration_id
                LEFT JOIN LATERAL (
                    SELECT ekr.id
                    FROM {SCHEMA}.ecomkassa_receipts ekr
                    WHERE ekr.company_id = ofd.company_id
                      AND ekr.removed_at IS NULL
                      AND ofd.fn_number IS NOT NULL
                      AND ofd.doc_number IS NOT NULL
                      AND (ofd.raw_data->>'DecimalFiscalSign') IS NOT NULL
                      AND (ekr.raw_data->'payload'->>'fn_number') = ofd.fn_number
                      AND (ekr.raw_data->'payload'->>'fiscal_document_number') = ofd.doc_number
                      AND (ekr.raw_data->'payload'->>'fiscal_document_attribute') = (ofd.raw_data->>'DecimalFiscalSign')
                    LIMIT 1
                ) km ON true
                WHERE ofd.company_id = %(company_id)s AND ofd.removed_at IS NULL
            ''')

        if wants(type_filter, 'receipt_kassa'):
            parts.append(f'''
                SELECT
                    'receipt_kassa' AS type,
                    'ecomkassa' AS source,
                    ekr.id AS id,
                    ekr.doc_datetime AS occurred_at,
                    NULL::date AS settlement_date,
                    ekr.total_sum AS amount,
                    ekr.status AS status,
                    ('KIND|' || COALESCE(
                        om.operation_type,
                        CASE WHEN ekr.is_sale IS NOT NULL THEN CASE WHEN ekr.is_sale THEN 'Income' ELSE 'Refund Income' END END,
                        CASE WHEN ad.operation LIKE 'sell_refund%%' THEN 'Refund Income' END,
                        ekr.raw_data->'payload'->>'operation_type', '') || '|' ||
                        CASE WHEN COALESCE(ekr.is_correction, ad.operation LIKE '%%correction', false) THEN '1' ELSE '0' END || '|' ||
                        COALESCE(ekr.doc_number, ekr.order_id, ekr.id::text)) AS title,
                    CASE WHEN ekr.order_type = 'CORD' AND ad.operation LIKE 'sell_refund%%' THEN 'Закрывающий чек возврата'
                         WHEN ekr.order_type = 'CORD' THEN 'Закрывающий чек заказа'
                         WHEN ad.operation LIKE 'sell_refund%%' OR rp.id IS NOT NULL THEN 'Чек возврата'
                         ELSE COALESCE(ekr.payment_provider, 'Касса') END AS subtitle,
                    ui.integration_name AS integration_name,
                    ekr.order_id AS reference,
                    ekr.raw_data AS raw_data,
                    -- Закрывающий чек заказа -> его заказ; чек, пробитый сценарием без заказа, или
                    -- чек возврата Т-Банка -> платёж-основание; иначе -> чек ОФД (чек ОФД и сам
                    -- ищет чек кассы по фискальным реквизитам, поэтому в группу попадёт всегда).
                    CASE WHEN ekr.order_type = 'CORD' THEN 'receipt_order'
                         WHEN ad.payment_row_id IS NOT NULL OR rp.id IS NOT NULL THEN 'payment'
                         WHEN om.id IS NOT NULL THEN 'receipt_ofd' END AS linked_type,
                    CASE WHEN ekr.order_type = 'CORD' THEN 'ecomkassa'
                         WHEN ad.payment_row_id IS NOT NULL OR rp.id IS NOT NULL THEN COALESCE(ad.payment_source, rp.source)
                         WHEN om.id IS NOT NULL THEN 'ofd' END AS linked_source,
                    CASE WHEN ekr.order_type = 'CORD' THEN ekr.id
                         ELSE COALESCE(ad.payment_row_id, rp.id, om.id) END AS linked_id,
                    CASE WHEN ekr.order_type = 'CORD' THEN 'order_receipt'
                         WHEN ad.payment_row_id IS NOT NULL THEN 'automation'
                         WHEN rp.id IS NOT NULL THEN 'refund_receipt'
                         WHEN om.id IS NOT NULL THEN 'fiscal_triplet' END AS match_method,
                    NULL::text AS group_key,
                    COALESCE(om.operation_type,
                             CASE WHEN ad.operation LIKE 'sell_refund%%' THEN 'Refund Income' END,
                             ekr.raw_data->'payload'->>'operation_type') AS linked_ofd_status
                FROM {SCHEMA}.ecomkassa_receipts ekr
                JOIN {SCHEMA}.user_integrations ui ON ui.id = ekr.integration_id
                LEFT JOIN LATERAL (
                    SELECT ofd.id, ofd.operation_type
                    FROM {SCHEMA}.ofd_receipts ofd
                    WHERE ofd.company_id = ekr.company_id
                      AND ofd.removed_at IS NULL
                      AND (ekr.raw_data->'payload'->>'fn_number') IS NOT NULL
                      AND (ekr.raw_data->'payload'->>'fiscal_document_number') IS NOT NULL
                      AND (ekr.raw_data->'payload'->>'fiscal_document_attribute') IS NOT NULL
                      AND ofd.fn_number = (ekr.raw_data->'payload'->>'fn_number')
                      AND ofd.doc_number = (ekr.raw_data->'payload'->>'fiscal_document_number')
                      AND (ofd.raw_data->>'DecimalFiscalSign') = (ekr.raw_data->'payload'->>'fiscal_document_attribute')
                    LIMIT 1
                ) om ON true
                LEFT JOIN LATERAL (
                    SELECT d.payment_row_id, d.operation, pp.slug AS payment_source
                    FROM {SCHEMA}.automation_documents d
                    LEFT JOIN {SCHEMA}.webhook_payments wp ON wp.id = d.payment_row_id AND wp.removed_at IS NULL
                    LEFT JOIN {SCHEMA}.user_integrations pui ON pui.id = wp.integration_id
                    LEFT JOIN {SCHEMA}.integration_providers pp ON pp.id = pui.provider_id
                    WHERE d.receipt_id = ekr.id AND d.company_id = ekr.company_id
                    ORDER BY d.id DESC LIMIT 1
                ) ad ON true
                LEFT JOIN LATERAL (
                    -- Чек возврата от Т-Банка: платёж-основание по PaymentId из уведомления.
                    SELECT wp.id, pp.slug AS source
                    FROM {SCHEMA}.webhook_payments wp
                    JOIN {SCHEMA}.user_integrations pui ON pui.id = wp.integration_id
                    JOIN {SCHEMA}.integration_providers pp ON pp.id = pui.provider_id
                    WHERE ekr.source = 'tbank'
                      AND lower(COALESCE(ekr.raw_data->'payload'->>'operation_type', 'income')) <> 'income'
                      AND wp.integration_id = ekr.integration_id
                      AND wp.payment_id = ekr.raw_data->'tbank_notification'->>'PaymentId'
                      AND wp.removed_at IS NULL
                    ORDER BY wp.id LIMIT 1
                ) rp ON true
                WHERE ekr.company_id = %(company_id)s AND ekr.removed_at IS NULL
                  -- Закрывающий чек заказа (CORD) - отдельная строка, связанная со своим заказом;
                  -- чек ОФД привязывается к нему сам по фискальным реквизитам.
                  AND (ekr.order_type IS NULL OR ekr.order_type IN ('VCHR', 'INVC')
                       OR (ekr.order_type = 'CORD' AND ekr.status = 'done'))
            ''')

        if wants(type_filter, 'receipt_order'):
            parts.append(f'''
                SELECT
                    'receipt_order' AS type,
                    'ecomkassa' AS source,
                    ekr.id AS id,
                    LEAST(ekr.created_at, ekr.doc_datetime) AS occurred_at,
                    NULL::date AS settlement_date,
                    ekr.total_sum AS amount,
                    ekr.status AS status,
                    ('Заказ #' || COALESCE(ekr.order_id, ekr.id::text)) AS title,
                    CASE WHEN aj.operation LIKE 'sell_refund%%' THEN 'Заказ на возврат'
                         ELSE COALESCE(ekr.payment_provider, 'Курьерский заказ') END AS subtitle,
                    ui.integration_name AS integration_name,
                    ekr.order_id AS reference,
                    ekr.raw_data AS raw_data,
                    CASE WHEN aj.payment_row_id IS NOT NULL THEN 'payment' WHEN ad.deal_id IS NOT NULL THEN 'crm_deal' END AS linked_type,
                    CASE WHEN aj.payment_row_id IS NOT NULL THEN aj.payment_source ELSE ad.deal_source END AS linked_source,
                    COALESCE(aj.payment_row_id, ad.deal_id) AS linked_id,
                    CASE WHEN aj.payment_row_id IS NOT NULL THEN 'automation' WHEN ad.deal_id IS NOT NULL THEN 'crm_automation' END AS match_method,
                    NULL::text AS group_key,
                    COALESCE(CASE WHEN aj.operation LIKE 'sell_refund%%' THEN 'Refund Income' END,
                             om.operation_type) AS linked_ofd_status
                FROM {SCHEMA}.ecomkassa_receipts ekr
                JOIN {SCHEMA}.user_integrations ui ON ui.id = ekr.integration_id
                LEFT JOIN LATERAL (
                    SELECT ofd.id, ofd.operation_type
                    FROM {SCHEMA}.ofd_receipts ofd
                    WHERE ofd.company_id = ekr.company_id
                      AND ofd.removed_at IS NULL
                      AND (ekr.raw_data->'payload'->>'fn_number') IS NOT NULL
                      AND (ekr.raw_data->'payload'->>'fiscal_document_number') IS NOT NULL
                      AND (ekr.raw_data->'payload'->>'fiscal_document_attribute') IS NOT NULL
                      AND ofd.fn_number = (ekr.raw_data->'payload'->>'fn_number')
                      AND ofd.doc_number = (ekr.raw_data->'payload'->>'fiscal_document_number')
                      AND (ofd.raw_data->>'DecimalFiscalSign') = (ekr.raw_data->'payload'->>'fiscal_document_attribute')
                    LIMIT 1
                ) om ON true
                LEFT JOIN LATERAL (
                    -- Заказ создан сценарием: реестр документов автоматизации хранит
                    -- платёж-основание, наш external_id и UUID заказа в кассе.
                    SELECT d.payment_row_id, d.operation, pp.slug AS payment_source
                    FROM {SCHEMA}.automation_documents d
                    JOIN {SCHEMA}.webhook_payments wp ON wp.id = d.payment_row_id AND wp.removed_at IS NULL
                    JOIN {SCHEMA}.user_integrations pui ON pui.id = wp.integration_id AND pui.status NOT IN ('deleted', 'hidden')
                    JOIN {SCHEMA}.integration_providers pp ON pp.id = pui.provider_id
                    WHERE d.company_id = ekr.company_id AND d.kassa_integration_id = ekr.integration_id
                      AND (d.ecom_uuid = ekr.order_id OR d.external_id = (ekr.raw_data->>'external_id'))
                    ORDER BY d.id DESC LIMIT 1
                ) aj ON true
                LEFT JOIN LATERAL (
                    -- Заказ создан сценарием по сделке CRM - в группу сделки.
                    SELECT cd.id AS deal_id, cd.provider_slug AS deal_source
                    FROM {SCHEMA}.automation_documents d
                    JOIN {SCHEMA}.automation_jobs j ON j.id = d.job_id AND j.source_type = 'crm_deal'
                    JOIN {SCHEMA}.automation_scenarios s ON s.id = j.scenario_id
                    JOIN {SCHEMA}.crm_deals cd ON cd.integration_id = s.source_integration_id
                         AND cd.external_deal_id = j.source_id AND cd.company_id = ekr.company_id
                         AND cd.removed_at IS NULL
                    WHERE d.company_id = ekr.company_id AND d.kassa_integration_id = ekr.integration_id
                      AND d.ecom_uuid = ekr.order_id
                    ORDER BY d.id DESC LIMIT 1
                ) ad ON true
                WHERE ekr.company_id = %(company_id)s AND ekr.removed_at IS NULL
                  AND ekr.order_type = 'CORD'
            ''')

        if wants(type_filter, 'crm_deal'):
            # Сделка CRM - шапка группы. Связь, по приоритету:
            # 1) заказ Екомкассы, созданный сценарием «Заказ в CRM» по этой сделке (UUID заказа
            #    в реестре документов автоматизации) - сделка в группе сразу с момента создания
            #    заказа, платежи и чеки по заказу подтягиваются по цепочке;
            # 2) чек/счёт по почте покупателя + сумме + ±5 минут от хука (crm_link.py).
            # Несвязанные сделки в реестр не попадают.
            parts.append(f'''
                SELECT
                    'crm_deal' AS type,
                    cd.provider_slug AS source,
                    cd.id AS id,
                    cd.created_at AS occurred_at,
                    NULL::date AS settlement_date,
                    cd.amount AS amount,
                    CASE WHEN lr.id IS NULL AND ao.id IS NOT NULL AND ao.status <> 'done' THEN 'wait' ELSE 'paid' END AS status,
                    ('Сделка #' || cd.external_deal_id) AS title,
                    cd.title AS subtitle,
                    ui.integration_name AS integration_name,
                    cd.external_deal_id AS reference,
                    jsonb_build_object('deal_id', cd.external_deal_id, 'title', cd.title, 'stage', cd.stage,
                                       'customer_emails', cd.customer_emails, 'linked_at', cd.linked_at,
                                       'order_uuid', ao.order_id) AS raw_data,
                    CASE WHEN lr.id IS NULL THEN 'receipt_order' WHEN lr.order_type = 'CORD' THEN 'receipt_order' ELSE 'receipt_kassa' END AS linked_type,
                    'ecomkassa' AS linked_source,
                    COALESCE(lr.id, ao.id) AS linked_id,
                    CASE WHEN lr.id IS NULL THEN 'crm_automation'
                         WHEN (lr.raw_data->'invoice_payload'->>'link') LIKE 'http%%' AND EXISTS (
                              SELECT 1 FROM jsonb_each_text(cd.raw_data) f
                              WHERE f.value = lr.raw_data->'invoice_payload'->>'link') THEN 'crm_pay_link'
                         ELSE 'crm_email' END AS match_method,
                    NULL::text AS group_key,
                    NULL::text AS linked_ofd_status
                FROM {SCHEMA}.crm_deals cd
                JOIN {SCHEMA}.user_integrations ui ON ui.id = cd.integration_id AND cd.removed_at IS NULL
                LEFT JOIN {SCHEMA}.ecomkassa_receipts lr ON lr.id = cd.linked_receipt_id AND lr.removed_at IS NULL
                LEFT JOIN LATERAL (
                    SELECT ekr.id, ekr.status, ekr.order_id
                    FROM {SCHEMA}.automation_documents d
                    JOIN {SCHEMA}.automation_jobs j ON j.id = d.job_id
                    JOIN {SCHEMA}.automation_scenarios s ON s.id = j.scenario_id
                    JOIN {SCHEMA}.ecomkassa_receipts ekr ON ekr.integration_id = d.kassa_integration_id
                         AND ekr.order_id = d.ecom_uuid AND ekr.order_type = 'CORD' AND ekr.removed_at IS NULL
                    WHERE d.company_id = cd.company_id AND j.source_type = 'crm_deal'
                      AND j.source_id = cd.external_deal_id AND s.source_integration_id = cd.integration_id
                      AND d.operation NOT LIKE 'sell_refund%%'
                    ORDER BY d.id DESC LIMIT 1
                ) ao ON true
                WHERE cd.company_id = %(company_id)s
                  AND (ao.id IS NOT NULL OR lr.id IS NOT NULL OR cd.candidate_receipt_id IS NOT NULL
                       OR EXISTS (SELECT 1 FROM {SCHEMA}.manual_transaction_links ml
                                  WHERE ml.company_id = cd.company_id AND ml.tx_type = 'crm_deal'
                                    AND ml.tx_id = cd.id))
            ''')

        if wants(type_filter, 'money'):
            parts.append(f'''
                SELECT
                    'money' AS type,
                    bst.provider_slug AS source,
                    bst.id AS id,
                    bst.operation_date AS occurred_at,
                    bst.settlement_date AS settlement_date,
                    bst.amount AS amount,
                    bst.direction AS status,
                    COALESCE(bst.counterparty_name, 'Операция по счёту') AS title,
                    COALESCE(bst.purpose, '') AS subtitle,
                    ui.integration_name AS integration_name,
                    bst.external_transaction_id AS reference,
                    bst.raw_data AS raw_data,
                    CASE
                        WHEN bst.parent_transaction_id IS NOT NULL THEN 'money'
                        WHEN lp.id IS NOT NULL OR wpm.id IS NOT NULL THEN 'payment'
                        WHEN rqr.id IS NOT NULL THEN 'receipt_kassa'
                        WHEN mm.id IS NOT NULL THEN 'money'
                    END AS linked_type,
                    CASE
                        WHEN bst.parent_transaction_id IS NOT NULL THEN bst.provider_slug
                        WHEN lp.id IS NOT NULL THEN lp.provider_slug
                        WHEN wpm.id IS NOT NULL THEN wpm.provider_slug
                        WHEN rqr.id IS NOT NULL THEN 'ecomkassa'
                        WHEN mm.id IS NOT NULL THEN mm.provider_slug
                    END AS linked_source,
                    COALESCE(bst.parent_transaction_id, lp.id, wpm.id, rqr.id, mm.id) AS linked_id,
                    CASE
                        WHEN bst.parent_transaction_id IS NOT NULL THEN 'acquiring_commission'
                        WHEN lp.id IS NOT NULL THEN 'settlement_date'
                        WHEN wpm.id IS NOT NULL THEN wpm.match_method
                        WHEN rqr.id IS NOT NULL THEN 'qr_id'
                        WHEN mm.id IS NOT NULL THEN 'qr_id'
                    END AS match_method,
                    NULL::text AS group_key,
                    NULL::text AS linked_ofd_status
                FROM {SCHEMA}.bank_statement_transactions bst
                JOIN {SCHEMA}.user_integrations ui ON ui.id = bst.integration_id
                -- Связь зачисления эквайринга с платежом, проставленная при
                -- синхронизации выписки (bank-statement-sync/acquiring_settlement).
                LEFT JOIN LATERAL (
                    SELECT lwp.id, lp_p.slug AS provider_slug
                    FROM {SCHEMA}.webhook_payments lwp
                    JOIN {SCHEMA}.user_integrations lp_ui ON lp_ui.id = lwp.integration_id
                    JOIN {SCHEMA}.integration_providers lp_p ON lp_p.id = lp_ui.provider_id
                    WHERE lwp.id = bst.linked_payment_id
                ) lp ON true
                LEFT JOIN LATERAL (
                    -- Банковская выписка сама по себе не содержит номер заказа -
                    -- назначение платежа (purpose) единственная зацепка. У платежей
                    -- через СБП (Точка/QR) банк пишет "QR ID <код>" - тот же код
                    -- есть в invoice_payload.link платежа Екомкассы (хвост ссылки
                    -- вида https://web.qr.nspk.ru/<код>). У эквайринга Т-Банка в
                    -- purpose приходит "Платеж <external_id>" - тот же external_id,
                    -- что Екомкасса передавала банку при создании платежа, и он же
                    -- сохранён в webhook_payments.raw_data->>'external_id'.
                    -- Оба совпадения достаточно специфичны (случайное совпадение
                    -- по 20+ символьному QR-коду или UUID/строке external_id
                    -- практически исключено), поэтому здесь, в отличие от
                    -- сопоставления по сумме/дате, это безопасно делать автоматически.
                    SELECT wp.id, p.slug AS provider_slug,
                           CASE WHEN qr_match.id IS NOT NULL THEN 'qr_id' ELSE 'external_id' END AS match_method
                    FROM {SCHEMA}.webhook_payments wp
                    JOIN {SCHEMA}.user_integrations wp_ui ON wp_ui.id = wp.integration_id
                    JOIN {SCHEMA}.integration_providers p ON p.id = wp_ui.provider_id
                    LEFT JOIN LATERAL (
                        SELECT wp.id
                        WHERE substring(bst.purpose FROM 'QR\\s*(?:коду\\s+)?ID\\s+([A-Za-z0-9]+)') IS NOT NULL
                          AND regexp_replace(regexp_replace(wp.raw_data->'invoice_payload'->>'link', '\\?.*$', ''), '^.*/', '')
                              = substring(bst.purpose FROM 'QR\\s*(?:коду\\s+)?ID\\s+([A-Za-z0-9]+)')
                    ) qr_match ON true
                    WHERE wp.company_id = bst.company_id AND wp.removed_at IS NULL
                      AND (
                        qr_match.id IS NOT NULL
                        OR (
                          substring(bst.purpose FROM 'Платеж\\s+(\\S+)') IS NOT NULL
                          AND wp.raw_data->>'external_id' = substring(bst.purpose FROM 'Платеж\\s+(\\S+)')
                        )
                      )
                    ORDER BY qr_match.id IS NOT NULL DESC
                    LIMIT 1
                ) wpm ON true
                -- Запасная связь: платёж шлюза мог не прийти (нет уведомления),
                -- но чек Екомкассы по счёту СБП есть - в его invoice_payload.link
                -- тот же QR ID, что банк пишет в назначении. Связываем деньги с чеком.
                LEFT JOIN LATERAL (
                    SELECT ekq.id
                    FROM {SCHEMA}.ecomkassa_receipts ekq
                    WHERE wpm.id IS NULL
                      AND ekq.company_id = bst.company_id AND ekq.removed_at IS NULL
                      AND ekq.merged_into_id IS NULL
                      AND substring(bst.purpose FROM 'QR\\s*(?:коду\\s+)?ID\\s+([A-Za-z0-9]+)') IS NOT NULL
                      AND ekq.raw_data->'invoice_payload'->>'link' LIKE '%%/' || substring(bst.purpose FROM 'QR\\s*(?:коду\\s+)?ID\\s+([A-Za-z0-9]+)') || '%%'
                    ORDER BY ekq.is_correction IS TRUE, ekq.id
                    LIMIT 1
                ) rqr ON true
                -- Комиссия СБП приходит ОТДЕЛЬНОЙ строкой банковской выписки
                -- (не платежом Екомкассы), поэтому связь "приход <-> его
                -- комиссия" - это money<->money, а не money<->payment. Ищем
                -- вторую строку той же компании с тем же QR ID в purpose и
                -- противоположным направлением (приход ищет свою комиссию,
                -- комиссия ищет свой приход). Только запасной вариант - если
                -- сам платёж уже нашёлся через wpm, эта связка не нужна: тогда
                -- обе money-строки и так попадут в одну группу транзитивно
                -- через union-find на фронте (обе ссылаются на один payment).
                LEFT JOIN LATERAL (
                    SELECT bst2.id, bst2.provider_slug
                    FROM {SCHEMA}.bank_statement_transactions bst2
                    WHERE wpm.id IS NULL AND rqr.id IS NULL
                      AND bst2.id != bst.id
                      AND bst2.company_id = bst.company_id
                      AND bst2.removed_at IS NULL
                      AND bst2.direction != bst.direction
                      AND substring(bst.purpose FROM 'QR\\s*(?:коду\\s+)?ID\\s+([A-Za-z0-9]+)') IS NOT NULL
                      AND substring(bst2.purpose FROM 'QR\\s*(?:коду\\s+)?ID\\s+([A-Za-z0-9]+)')
                          = substring(bst.purpose FROM 'QR\\s*(?:коду\\s+)?ID\\s+([A-Za-z0-9]+)')
                    LIMIT 1
                ) mm ON true
                WHERE bst.company_id = %(company_id)s AND bst.removed_at IS NULL
            ''')

        if not parts:
            return {
                'statusCode': 200,
                'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
                'body': json.dumps({'success': True, 'transactions': [], 'totals_by_type': {}, 'limit': limit, 'offset': offset}),
                'isBase64Encoded': False
            }

        # LIMIT/OFFSET намеренно не применяется в SQL: платежи с одним и тем же
        # номером схлопываются в одну транзакцию уже в Python (ниже), а обрезать
        # строки до этого схлопывания могло бы разбить одну группу пополам
        # между страницами. При типичных объёмах теста/демо это не проблема -
        # компания вряд ли накопит десятки тысяч транзакций.
        union_query = ' UNION ALL '.join(parts)
        full_query = f'''
            WITH all_tx AS ({union_query})
            SELECT * FROM all_tx
            ORDER BY occurred_at DESC NULLS LAST
        '''

        cur.execute(full_query, {'company_id': company_id})
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

        # Ручные связи (кнопка "Связать" в реестре) - раскладываем в словарь
        # (type, source, id) -> link_group_id, чтобы приклеить каждой
        # транзакции её manual_group_id ниже. Группировка по этому полю
        # выполняется уже на фронте (transactionGrouping.ts), тем же
        # union-find, что и для автоматических связей.
        cur.execute(f'''
            SELECT tx_type, tx_source, tx_id, link_group_id::text
            FROM {SCHEMA}.manual_transaction_links
            WHERE company_id = %(company_id)s
        ''', {'company_id': company_id})
        manual_links = {(t, s, i): g for t, s, i, g in cur.fetchall()}

        # Записи, выведенные пользователем из группы ("разорвать связь") -
        # фронт не склеивает их автоматическими связями ни в одну сторону.
        cur.execute(f'''
            SELECT tx_type, tx_source, tx_id
            FROM {SCHEMA}.transaction_link_exclusions
            WHERE company_id = %(company_id)s
        ''', {'company_id': company_id})
        link_exclusions = {(t, s, i) for t, s, i in cur.fetchall()}

        # Схлопывание вебхуков одного платежа (payment_id/order_id) в одну
        # транзакцию. Строки уже отсортированы occurred_at DESC на уровне SQL,
        # поэтому первая встреченная строка группы - самая свежая (её статус,
        # сумма и raw_data берём как представление всей группы), а остальные
        # уходят в webhook_history. Порядок появления групп в final_rows
        # совпадает с глобальным порядком occurred_at DESC - пересортировка
        # после схлопывания не нужна.
        payment_groups: Dict[Any, Dict[str, Any]] = {}
        final_rows = []
        # Вебхуки одного платежа, схлопнутые в шапку: (source, id) -> id шапки - чтобы связи
        # чеков с любым статусом платежа (чек продажи пробит по CONFIRMED) вели в группу.
        payment_alias: Dict[Tuple[str, int], int] = {}

        for row in rows:
            tx = {}
            for col, val in zip(columns, row):
                tx[col] = to_json_value(val)

            group_key = tx.pop('group_key', None)

            if tx['type'] == 'payment':
                # Отмена/возврат - отдельная операция в группе платежа (деньги ушли обратно),
                # остальные статусы (удержан, оплачен, отклонён) схлопываются в шапку продажи.
                op = 'refund' if tx.get('status') in REFUND_STATUSES and group_key else 'sale'
                gkey = (tx['source'], group_key or f"id:{tx['id']}", op)
                group = payment_groups.get(gkey)
                if group is None:
                    group = tx
                    group['webhook_history'] = [{'status': tx['status'], 'occurred_at': tx['occurred_at']}]
                    group['_aliases'] = []
                    if op == 'refund':
                        group['payment_operation'] = 'refund'
                    payment_groups[gkey] = group
                    final_rows.append(group)
                else:
                    group['webhook_history'].append({'status': tx['status'], 'occurred_at': tx['occurred_at']})
                    group['_aliases'].append(tx['id'])
                    payment_alias[(tx['source'], tx['id'])] = group['id']
                    if tx.get('linked_id') and not group.get('linked_id'):
                        group['linked_type'] = tx['linked_type']
                        group['linked_source'] = tx['linked_source']
                        group['linked_id'] = tx['linked_id']
                        group['match_method'] = tx['match_method']
            else:
                final_rows.append(tx)

        for (source, key, op), group in payment_groups.items():
            if op != 'refund':
                continue
            sale = payment_groups.get((source, key, 'sale'))
            group['title'] = ('Возврат платежа #' if group.get('status') == 'REFUNDED' else 'Отмена платежа #') + \
                str(group.get('title') or '').replace('Платёж #', '', 1)
            if not sale:
                # Отмена без продажи (счёт не оплатили) - деньги не двигались, это не возврат.
                group.pop('payment_operation', None)
                group['title'] = 'Платёж #' + str(group['title']).split('#', 1)[-1]
                continue
            sale['_refunded'] = True
            if sale:
                group['linked_type'] = 'payment'
                group['linked_source'] = source
                group['linked_id'] = sale['id']
                group['match_method'] = 'payment_refund'

        for row in final_rows:
            if row.get('linked_type') == 'payment' and row.get('linked_id') is not None:
                head = payment_alias.get((row.get('linked_source'), row['linked_id']))
                if head is not None:
                    row['linked_id'] = head

        for group in payment_groups.values():
            group['webhook_history'].reverse()
            if len(group['webhook_history']) <= 1:
                del group['webhook_history']

        for row in final_rows:
            row['title'] = receipt_kind_title(row.get('title'))
            row['signed_amount'] = compute_signed_amount(row)
            row.pop('linked_ofd_status', None)
            ids = [row['id']] + row.pop('_aliases', [])
            row['manual_group_id'] = next((manual_links[(row['type'], row['source'], i)] for i in ids
                                           if (row['type'], row['source'], i) in manual_links), None)
            row['link_excluded'] = any((row['type'], row['source'], i) in link_exclusions for i in ids)

        if not paged:
            for t in final_rows:
                t.pop('_refunded', None)
            totals_by_type: Dict[str, Dict[str, Any]] = {}
            for row in final_rows:
                bucket = totals_by_type.setdefault(row['type'], {'count': 0, 'amount': 0.0, 'matched_count': 0})
                bucket['count'] += 1
                bucket['amount'] += row['signed_amount']
                if row.get('linked_id'):
                    bucket['matched_count'] += 1
            return json_ok({
                'success': True,
                'transactions': final_rows[offset:offset + limit],
                'totals_by_type': totals_by_type,
                'limit': limit,
                'offset': offset
            })

        # Постраничный режим реестра: фильтры применяются на сервере ко ВСЕЙ
        # базе, итоги плиток считаются по всем отфильтрованным записям, а
        # отдаётся порция групп (группа никогда не режется между страницами).
        company_tz = ZoneInfo(DEFAULT_TZ)
        cur.execute(f'SELECT timezone FROM {SCHEMA}.companies WHERE id = %(company_id)s', {'company_id': company_id})
        tz_row = cur.fetchone()
        if tz_row and tz_row[0]:
            try:
                company_tz = ZoneInfo(tz_row[0])
            except Exception:
                pass

        all_groups = group_transactions(final_rows)

        if params.get('status_summary') == '1':
            # Статус сверки за период (по часовому поясу компании) - считаем сделки:
            # оплаченный платёж + чек в группе = сверено; платёж без чека, но с
            # заказом в кассе = ожидает чек; платёж без чека и заказа = без чека;
            # чек кассы без платежа в группе = чек без платежа.
            def in_period(t):
                day = local_date(t.get('occurred_at'), company_tz)
                return bool(day) and (not date_from or day >= date_from) and (not date_to or day <= date_to)

            summary = {k: {'count': 0, 'amount': 0.0} for k in ('reconciled', 'waiting', 'no_receipt', 'no_payment')}
            for g in all_groups:
                has_receipt = any(t['type'] in ('receipt_kassa', 'receipt_ofd') for t in g)
                has_order = any(t['type'] == 'receipt_order' for t in g)
                paid = [t for t in g if t['type'] == 'payment' and t.get('status') in ('CONFIRMED', 'AUTHORIZED')
                        and not t.get('_refunded')]
                if paid:
                    bucket = 'reconciled' if has_receipt else ('waiting' if has_order else 'no_receipt')
                    for t in paid:
                        if in_period(t):
                            summary[bucket]['count'] += 1
                            summary[bucket]['amount'] += float(t.get('amount') or 0)
                    continue
                if any(t['type'] == 'payment' for t in g):
                    continue
                for t in g:
                    if t['type'] == 'receipt_kassa' and t.get('status') == 'done' and in_period(t) \
                            and float(t.get('signed_amount') or 0) > 0 and t.get('match_method') != 'order_receipt':
                        summary['no_payment']['count'] += 1
                        summary['no_payment']['amount'] += float(t.get('amount') or 0)
            for v in summary.values():
                v['amount'] = round(v['amount'], 2)
            return json_ok({'success': True, 'summary': summary})

        if params.get('missing_receipts') == '1':
            # Проверка для уведомлений: оплаченные платежи за день (по часовому поясу
            # компании), в группе которых нет ни одного чека - ни кассы, ни ОФД.
            # older_than_min/newer_than_hours - для сценария «Расхождение»: платежи без чека,
            # с оплаты которых прошло не меньше N минут (но не старше окна, чтобы не тянуть историю).
            day = params.get('date')
            older_min = params.get('older_than_min')
            newer_hours = params.get('newer_than_hours')
            now_utc = datetime.utcnow()
            missing = []
            for g in all_groups:
                if any(t['type'] in ('receipt_kassa', 'receipt_ofd') for t in g):
                    continue
                for t in g:
                    if t['type'] != 'payment' or t.get('status') not in ('CONFIRMED', 'AUTHORIZED') or t.get('_refunded'):
                        continue
                    if day and local_date(t.get('occurred_at'), company_tz) != day:
                        continue
                    if older_min or newer_hours:
                        paid_at = datetime.fromisoformat(str(t.get('occurred_at'))).replace(tzinfo=None) \
                            if t.get('occurred_at') else None
                        if not paid_at:
                            continue
                        if older_min and paid_at > now_utc - timedelta(minutes=int(older_min)):
                            continue
                        if newer_hours and paid_at < now_utc - timedelta(hours=int(newer_hours)):
                            continue
                    missing.append({'id': t['id'], 'title': t['title'], 'amount': t.get('amount'),
                                    'integration_name': t.get('integration_name'),
                                    'occurred_at': t.get('occurred_at')})
            return json_ok({'success': True, 'date': day, 'payments': missing,
                            'count': len(missing),
                            'amount': round(sum(float(m['amount'] or 0) for m in missing), 2)})

        matched = set()
        for g in all_groups:
            if len(g) > 1:
                matched.update(node_key(t) for t in g)
        group_of = {}
        for g in all_groups:
            for t in g:
                group_of[node_key(t)] = g

        for t in final_rows:
            t.pop('_refunded', None)

        filtered = [
            t for t in final_rows
            if (not types_filter or t['type'] in types_filter)
            and matches_filters(t, matched, unmatched_only, date_from, date_to, company_tz, search)
        ]

        totals_by_type = {}
        for row in filtered:
            bucket = totals_by_type.setdefault(row['type'], {'count': 0, 'amount': 0.0, 'matched_count': 0})
            bucket['count'] += 1
            bucket['amount'] += row['signed_amount']
            if node_key(row) in matched:
                bucket['matched_count'] += 1
        for bucket in totals_by_type.values():
            bucket['amount'] = round(bucket['amount'], 2)

        filtered_groups = group_transactions(filtered)
        filtered_groups.sort(key=latest_time, reverse=True)

        page_rows = []
        next_offset = offset
        while next_offset < len(filtered_groups) and len(page_rows) < limit:
            page_rows.extend(filtered_groups[next_offset])
            next_offset += 1

        page_keys = {node_key(t) for t in page_rows}
        context_rows = []
        seen = set(page_keys)
        for t in page_rows:
            for member in group_of.get(node_key(t), []):
                k = node_key(member)
                if k not in seen:
                    seen.add(k)
                    context_rows.append(member)

        return json_ok({
            'success': True,
            'transactions': page_rows,
            'context_transactions': context_rows,
            'totals_by_type': totals_by_type,
            'total_groups': len(filtered_groups),
            'total_count': len(filtered),
            'next_offset': next_offset,
            'has_more': next_offset < len(filtered_groups)
        })

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)}),
            'isBase64Encoded': False
        }
    finally:
        cur.close()
        conn.close()
import json
import re
import os
import psycopg2
from typing import Dict, Any, Optional
from datetime import datetime, date, timedelta
from auth_guard import guard

SCHEMA = 't_p83864310_fintech_payment_reco'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}


def parse_date(value: str, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return fallback



def short_kind_name(description: Optional[str]) -> str:
    '''
    Короткое название вида оплаты для отчёта: без «Платёж через» и «счёт»,
    кавычки - ёлочки, а если в кавычках всё название - без них.
    «Платёж через счёт "Тинькофф Эквайринг"» -> «Тинькофф Эквайринг».
    '''
    text = re.sub(r'^\s*плат[её]ж\s+через\s+', '', description or '', flags=re.IGNORECASE)
    text = re.sub(r'^сч[её]т\s+', '', text, flags=re.IGNORECASE).strip()
    m = re.fullmatch(r'["«](.+)["»]', text)
    if m:
        text = m.group(1)
    text = re.sub(r'"([^"]*)"', r'«\1»', text)
    return (text[:1].upper() + text[1:]) if text else (description or '')


def short_kind_label(label: str) -> str:
    '''
    Короткое название вида оплаты из справочника кассы:
    «Платёж через счёт "Тинькофф СБП"» -> «Тинькофф СБП»,
    «Платёж через СБП банка "Точка"» -> «СБП Точка», «Платёж через эквайринг банка "Точка"» -> «Эквайринг Точка».
    '''
    text = re.sub(r'^\s*плат[её]ж\s+через\s+', '', label, flags=re.IGNORECASE)
    if text == label:
        return label
    text = re.sub(r'^сч[её]т\s+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+банка\s+', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'["«»]', '', text).strip()
    return (text[:1].upper() + text[1:]) if text else label


def payment_kind_label(provider_slug: Optional[str], payment_provider: Optional[str],
                       integration_name: Optional[str], kind_names: Dict[str, str]) -> str:
    '''
    Строка блока «Детализация по видам оплат»: для шлюза Екомкассы - вид оплаты
    из справочника кассы (ecomkassa_payment_types) по коду шлюза, для остальных
    платёжек - название интеграции. Неизвестный код показываем как есть.
    '''
    name = integration_name or 'Платёжная интеграция'
    if provider_slug in ('ecomkassa_gateway', 'ecomkassa') and payment_provider:
        code = str(payment_provider).strip()
        label = kind_names.get(code.upper(), code)
        return short_kind_label(label)
    return name


def classify_receipt_sign(operation_type: Optional[str]) -> int:
    '''
    Знак вклада фискального документа в выручку по его типу операции (54-ФЗ) -
    та же классификация, что в transactions-list/compute_signed_amount, чтобы
    раздел "Сверка" и раздел "Транзакции" показывали одинаковые нетто-суммы.
    Income/приход = +, Refund income/возврат прихода = -, Expense/расход = -,
    Refund expense/возврат расхода = +. Неизвестный тип по умолчанию = приход.
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


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Сверка трёх точек контроля выручки компании за выбранный период:
    1) платежи, пришедшие вебхуками из интеграций эквайринга (webhook_payments,
       провайдеры категории "payments") - берём последний статус по каждому
       payment_id. Учитываются ТОЛЬКО активные интеграции (ui.status='active') -
       мягко удалённые/тестовые интеграции (напр. созданные при отладке
       soft-delete сценариев) не должны попадать в сверку реальных денег.
       Количество (payments_count) считается по числу платёжных документов
       вне зависимости от статуса, а сумма - НЕТТО: платёж вносит вклад
       только пока он реально "жив" деньгами (AUTHORIZED/CONFIRMED), возврат
       (REFUNDED) или отмена дают 0 - деньги пришли и ушли обратно, либо
       вообще не двигались.
    2) чеки - касса (ecomkassa_receipts) и ОФД (ofd_receipts) считаются и
       сравниваются МЕЖДУ СОБОЙ, а НЕ суммируются в одну точку - это два
       разных физических источника данных об одном и том же чеке (касса
       пробивает и пересылает результат сама, ОФД получает копию от
       налоговой), сложение их сумм задвоило бы каждую продажу. Оба - НЕТТО
       с учётом знака операции (Income/+, Refund income/-, по 54-ФЗ); у чека
       кассы нет собственного поля типа операции - знак берётся из связанного
       чека ОФД (по триплету фискальных реквизитов ФН+ФД+ФПД), без пары
       считается продажей (+), как и в разделе "Транзакции". Основная сумма
       "чеков" для сравнения с платежами и деньгами на р/с берётся из кассы
       (это источник, который реально формирует продажу в моменте), сумма
       ОФД идёт отдельным полем receipts_ofd для контроля кассы vs ОФД.
    3) реальные деньги, поступившие и списанные с расчётного счёта
       (bank_statement_transactions) - эти операции уже отфильтрованы по
       ключевым словам назначения платежа на этапе синхронизации выписки
       (это все "наши" операции терминала/счёта). Количество считается по
       числу операций, сумма - НЕТТО: direction='in' даёт +amount, 'out'
       (например, возврат клиенту со счёта) вычитается. Комиссия эквайринга
       возвращается обратно к сумме прихода (чтобы сравнивать с ВАЛОВОЙ
       выручкой чеков), распознаётся тремя способами по убыванию приоритета:
       заполненный реестр платежей терминала (commission_amount/source), текст
       "Справочно: сумма комиссии X руб" в purpose (классический эквайринг -
       банк платит одним зачислением за период, комиссия вычтена ДО выплаты и
       её сумма написана прямо в назначении), либо отдельная строка "Комиссия
       ... QR ID <код>" с тем же QR ID, что и приход (СБП - комиссия приходит
       отдельной операцией списания сразу за приходом, это две строки одной
       сделки, а не два независимых события).
    Дата события для платежа - дата ФАКТИЧЕСКОЙ фискальной операции (чек
    привязан - берём его doc_datetime), а не дата, когда запись физически
    появилась в нашей БД (created_at может быть сильно позже реальной оплаты
    при дозагрузке исторических документов) - иначе платёж "переезжает" на
    день загрузки и ложно расходится по дате с чеком.
    Результат сохраняется снапшотом в reconciliation_snapshots (upsert по
    company_id+period), чтобы не пересчитывать и в будущем показать детализацию.
    День "сегодня" в расчёт не берётся - сверяем только полностью закрытые дни,
    поэтому period_to не может быть позже вчера.
    Args: company_id (обязателен), date_from, date_to (YYYY-MM-DD, опционально)
    Returns: totals по трём точкам (НЕТТО-суммы, count - число документов;
    receipts.amount/count - касса, receipts.ofd_amount/ofd_count - ОФД),
    daily[] для графика, details для детализации
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
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    params = event.get('queryStringParameters', {}) or {}
    company_id = params.get('company_id')

    if not company_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'company_id required'}),
            'isBase64Encoded': False
        }

    yesterday = date.today() - timedelta(days=1)
    date_from = parse_date(params.get('date_from'), yesterday - timedelta(days=6))
    date_to = parse_date(params.get('date_to'), yesterday)

    # "Сегодня" в сверку никогда не попадает - сверяем только полностью
    # закрытые дни, за которые уже могли прийти и чек, и банковская выписка.
    if date_to > yesterday:
        date_to = yesterday
    if date_from > date_to:
        date_from = date_to

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    # Время платежей и чеков в базе - UTC; день считаем по часовому поясу компании
    # (как в «Транзакциях»), иначе вечерние операции уезжают на соседние сутки.
    tz_cur = conn.cursor()
    tz_cur.execute(f'''
        SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_timezone_names n WHERE n.name = c.timezone)
                    THEN c.timezone ELSE 'Europe/Moscow' END
        FROM {SCHEMA}.companies c WHERE c.id = %s
    ''', (company_id,))
    company_tz = (tz_cur.fetchone() or ['Europe/Moscow'])[0]
    tz_cur.close()
    cur = conn.cursor()

    try:
        # 1. Платежи: последний статус по каждому payment_id. Дата платежа -
        # первое появление вебхука (когда платёж был создан) для "живых"
        # платежей. НО для синтетических платежей, досозданных дозагрузкой
        # исторических документов (ecomkassa-fetch-orders/save_synthetic_payment) -
        # created_at это момент, когда пользователь нажал "Дозагрузить" (может
        # быть сильно позже реальной оплаты), поэтому для них берём реальную
        # дату фискальной операции из привязанного чека (ecomkassa_receipts.
        # doc_datetime, receipt_id уже проставлен при создании такого платежа) -
        # иначе платёж "переезжает" на день дозагрузки и выпадает из сверки за
        # реальный день продажи, создавая ложное расхождение с чеками.
        # Отмена/возврат оплаченного платежа - отдельная операция (минус в день отмены),
        # как в реестре транзакций: продажа и возврат сверяются со своими чеками по дням.
        cur.execute(f'''
            WITH rows AS (
                SELECT wp.*, ui.integration_name, p.slug AS provider_slug, er.doc_datetime AS receipt_dt,
                       CASE WHEN wp.status IN ('REFUNDED', 'CANCELED') AND EXISTS (
                                SELECT 1 FROM {SCHEMA}.webhook_payments s
                                WHERE s.integration_id = wp.integration_id AND s.payment_id = wp.payment_id
                                  AND s.status IN ('AUTHORIZED', 'CONFIRMED') AND s.removed_at IS NULL)
                            THEN 'refund' ELSE 'sale' END AS op
                FROM {SCHEMA}.webhook_payments wp
                JOIN {SCHEMA}.user_integrations ui ON ui.id = wp.integration_id
                JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
                JOIN {SCHEMA}.integration_categories c ON c.id = p.category_id
                LEFT JOIN {SCHEMA}.ecomkassa_receipts er ON er.id = wp.receipt_id
                WHERE wp.company_id = %s AND (c.slug = 'payments' OR p.slug = 'ecomkassa')
                  AND wp.removed_at IS NULL AND ui.status = 'active'
            ), latest AS (
                SELECT
                    integration_id, payment_id, op,
                    MAX(amount) AS amount,
                    MIN(((COALESCE(receipt_dt, created_at) AT TIME ZONE 'UTC') AT TIME ZONE %s)::date) AS payment_date,
                    CASE WHEN op = 'refund' THEN 'REFUND_OP'
                         WHEN bool_or(status IN ('AUTHORIZED', 'CONFIRMED')) THEN
                              (array_agg(status ORDER BY (status IN ('AUTHORIZED', 'CONFIRMED')) DESC, created_at DESC))[1]
                         ELSE (array_agg(status ORDER BY created_at DESC))[1] END AS latest_status,
                    (array_agg(payment_provider ORDER BY created_at DESC))[1] AS payment_provider,
                    MAX(integration_name) AS integration_name,
                    MAX(provider_slug) AS provider_slug,
                    (array_agg(status ORDER BY created_at DESC))[1] AS refund_status
                FROM rows
                GROUP BY integration_id, payment_id, op
            )
            SELECT payment_date, CASE WHEN latest_status = 'REFUND_OP' THEN refund_status ELSE latest_status END,
                   amount, payment_provider, integration_name, provider_slug, latest_status = 'REFUND_OP'
            FROM latest
            WHERE payment_date BETWEEN %s AND %s
        ''', (company_id, company_tz, date_from, date_to))

        payments_rows = cur.fetchall()
        cur.execute(f'''
            SELECT UPPER(provider_code), description FROM {SCHEMA}.ecomkassa_payment_types
            WHERE provider_code IS NOT NULL
        ''')
        kind_names = {code: short_kind_name(desc) for code, desc in cur.fetchall()}
        payments_total = 0.0
        payments_count = 0
        payments_by_status: Dict[str, int] = {}
        daily_payments: Dict[str, float] = {}
        # Детализация по видам оплат внутри шлюза Екомкассы (ЮKassa, СБП и т.п.) -
        # только по успешным платежам, у одной кассы их может быть больше 10.
        payments_by_provider: Dict[str, Dict[str, float]] = {}

        for payment_date, latest_status, amount, payment_provider, integration_name, provider_slug, is_refund in payments_rows:
            payments_by_status[latest_status] = payments_by_status.get(latest_status, 0) + 1
            # Количество - по числу документов вне зависимости от статуса
            # (возврат тоже был платежом и должен быть виден в счётчике).
            # Неоплаченные попытки (отклонён/истёк/отменён до оплаты) - не операции с деньгами,
            # чека по ним нет: в количество для сверки с чеками не входят.
            if is_refund or latest_status in ('AUTHORIZED', 'CONFIRMED'):
                payments_count += 1

            amount_f = float(amount) if amount else 0.0
            # Сумма - нетто: вклад в выручку только у реально подтверждённых
            # денег, возврат/отмена дают 0 (деньги не задержались на счету).
            # Отмена/возврат оплаченного платежа - минус в день отмены (продажа своё уже внесла).
            contribution = -amount_f if is_refund else (amount_f if latest_status in ('AUTHORIZED', 'CONFIRMED') else 0.0)
            payments_total += contribution

            day_key = payment_date.isoformat()
            daily_payments[day_key] = daily_payments.get(day_key, 0.0) + contribution

            if latest_status in ('AUTHORIZED', 'CONFIRMED') and not is_refund:
                provider_key = payment_kind_label(provider_slug, payment_provider, integration_name, kind_names)
                if provider_key not in payments_by_provider:
                    payments_by_provider[provider_key] = {'amount': 0.0, 'count': 0}
                payments_by_provider[provider_key]['amount'] += amount_f
                payments_by_provider[provider_key]['count'] += 1

        # 2. Чеки кассы (ecomkassa_receipts) и чеки ОФД (ofd_receipts) - ДВА
        # РАЗНЫХ источника данных об одном и том же физическом чеке, поэтому
        # считаются и сравниваются МЕЖДУ СОБОЙ, а не суммируются в одну точку
        # (сложение задвоило бы каждую продажу - касса пробивает чек и
        # присылает его нам сама, ОФД параллельно получает копию от налоговой
        # для того же самого чека). "receipts" (основная точка сверки с
        # платежами и деньгами на р/с) - это касса; ОФД - контрольная точка
        # для сравнения кассы vs ОФД, считается отдельно и возвращается как
        # receipts_ofd_total/receipts_ofd_count.
        cur.execute(f'''
            SELECT
                ((ekr.doc_datetime AT TIME ZONE 'UTC') AT TIME ZONE %s)::date AS receipt_date,
                ekr.total_sum,
                COALESCE(om.operation_type,
                         CASE WHEN adv.operation LIKE 'sell_refund%%' THEN 'Refund Income' END,
                         ekr.raw_data->'payload'->>'operation_type') AS linked_ofd_status,
                COALESCE(adv.advance_sum, 0) AS advance_sum
            FROM {SCHEMA}.ecomkassa_receipts ekr
            LEFT JOIN LATERAL (
                SELECT ofd.operation_type
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
                -- Документ создан сценарием (реестр документов автоматизации): часть суммы,
                -- оплаченная зачётом аванса, денег не приносит - её уже учёл чек оплаты.
                SELECT MAX(d.advance_sum) AS advance_sum, MAX(d.operation) AS operation
                FROM {SCHEMA}.automation_documents d
                WHERE d.company_id = ekr.company_id AND d.kassa_integration_id = ekr.integration_id
                  AND (d.receipt_id = ekr.id OR d.ecom_uuid = ekr.order_id)
            ) adv ON true
            WHERE ekr.company_id = %s
              AND ekr.removed_at IS NULL
              AND ekr.status IS DISTINCT FROM 'cancelled'
              AND ekr.status IS DISTINCT FROM 'wait'
              AND ((ekr.doc_datetime AT TIME ZONE 'UTC') AT TIME ZONE %s)::date BETWEEN %s AND %s
        ''', (company_tz, company_id, company_tz, date_from, date_to))

        receipts_rows = cur.fetchall()
        receipts_total = 0.0
        receipts_count = 0
        daily_receipts: Dict[str, float] = {}

        advance_offset_total = 0.0
        advance_offset_count = 0
        for receipt_date, total_sum, linked_ofd_status, advance_sum in receipts_rows:
            amount_f = float(total_sum) if total_sum else 0.0
            advance_f = min(float(advance_sum or 0), amount_f)
            if advance_f > 0:
                advance_offset_total += advance_f
                advance_offset_count += 1
                amount_f -= advance_f
                if amount_f <= 0:
                    continue
            signed = amount_f * classify_receipt_sign(linked_ofd_status)
            receipts_total += signed
            receipts_count += 1
            if receipt_date:
                day_key = receipt_date.isoformat()
                daily_receipts[day_key] = daily_receipts.get(day_key, 0.0) + signed

        # 2б. Чеки ОФД отдельно - контрольная точка "касса vs ОФД".
        cur.execute(f'''
            SELECT ofd.total_sum, ofd.operation_type, ((ofd.doc_datetime AT TIME ZONE 'UTC') AT TIME ZONE %s)::date
            FROM {SCHEMA}.ofd_receipts ofd
            WHERE ofd.company_id = %s
              AND ofd.removed_at IS NULL
              AND ((ofd.doc_datetime AT TIME ZONE 'UTC') AT TIME ZONE %s)::date BETWEEN %s AND %s
        ''', (company_tz, company_id, company_tz, date_from, date_to))

        receipts_ofd_total = 0.0
        receipts_ofd_count = 0
        daily_receipts_ofd: Dict[str, float] = {}
        for total_sum, operation_type, ofd_date in cur.fetchall():
            amount_f = float(total_sum) if total_sum else 0.0
            signed_ofd = amount_f * classify_receipt_sign(operation_type)
            receipts_ofd_total += signed_ofd
            receipts_ofd_count += 1
            if ofd_date:
                day_key = ofd_date.isoformat()
                daily_receipts_ofd[day_key] = daily_receipts_ofd.get(day_key, 0.0) + signed_ofd

        # 3. Деньги на р/с: обе стороны (in/out) - выписка уже отфильтрована по
        # ключевым словам назначения платежа на этапе синхронизации (это все
        # "наши" операции терминала/счёта). in = +amount, out = -amount
        # (например, возврат клиенту прямо со счёта или отдельная строка
        # комиссии СБП).
        #
        # КОМИССИЯ ЭКВАЙРИНГА - два физически разных способа, которыми банк
        # доносит её до выписки, и оба нужно вернуть обратно к сумме, чтобы
        # "Деньги" сравнивались с ВАЛОВОЙ выручкой чеков (а не с суммой уже за
        # вычетом комиссии - иначе разница на плитке всегда была бы отрицательной
        # и не значила бы никакой реальной проблемы):
        #   (а) классический эквайринг (карта, не СБП) - банк платит ОДНИМ
        #       зачислением за весь отчётный период (обычно раз в 1-2 дня, с
        #       опозданием), комиссия уже вычтена ДО зачисления и её сумма
        #       написана прямо в назначении платежа текстом "Справочно: сумма
        #       комиссии X руб" - извлекаем регексом прямо в SQL;
        #   (б) СБП (QR-платежи) - комиссия приходит ОТДЕЛЬНОЙ строкой выписки
        #       (direction='out', "Комиссия за осуществление переводов... QR ID
        #       <код>") сразу вслед за приходом с тем же QR ID в назначении -
        #       эта строка физически является частью той же сделки, не
        #       самостоятельным расходом, поэтому не вычитается из суммы
        #       "Денег", а прибавляется обратно (аналогично п. а).
        # commission_amount/commission_source (реестр платежей эквайринга,
        # если когда-нибудь будет подключён) остаются приоритетным источником
        # там, где заполнены - оба текстовых способа ниже лишь запасной вариант
        # на случай, если реестра нет (как сейчас).
        cur.execute(f'''
            SELECT
                COALESCE(bst.settlement_date, bst.operation_date::date) AS op_date,
                bst.amount,
                bst.direction,
                bst.purpose,
                COALESCE(bst.commission_amount, 0) AS commission_amount,
                bst.commission_source,
                substring(bst.purpose FROM 'сумма комиссии\\s+([\\d.,]+)\\s*руб') AS acquiring_commission_text,
                substring(bst.purpose FROM 'QR\\s*(?:коду\\s+)?ID\\s+([A-Za-z0-9]+)') AS qr_id,
                (bst.purpose ILIKE 'Комиссия%%QR ID%%' OR bst.purpose ILIKE 'Комиссия%%СБП%%') AS is_sbp_commission_row
            FROM {SCHEMA}.bank_statement_transactions bst
            JOIN {SCHEMA}.user_integrations ui ON ui.id = bst.integration_id
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            JOIN {SCHEMA}.integration_categories c ON c.id = p.category_id
            WHERE bst.company_id = %s AND c.slug = 'banks'
              AND bst.removed_at IS NULL
              -- Расчётная строка комиссии эквайринга (создаётся при синхронизации
              -- для наглядности в группе) - не реальное списание со счёта, её
              -- сумма уже учтена через commission_amount самого зачисления.
              AND bst.parent_transaction_id IS NULL
              -- Зачисление эквайринга относится к дню продаж ("за ДД.ММ.ГГГГ"
              -- в назначении), а не к дню поступления денег.
              AND COALESCE(bst.settlement_date, bst.operation_date::date) BETWEEN %s AND %s
        ''', (company_id, date_from, date_to))

        bank_rows = cur.fetchall()
        bank_raw_total = 0.0
        bank_commission_total = 0.0
        bank_count = 0
        bank_with_known_commission = 0
        daily_bank: Dict[str, float] = {}
        daily_commission: Dict[str, float] = {}

        # bank_raw_total - ЛИТЕРАЛЬНЫЙ чистый эффект на остаток счёта (как есть
        # по выписке): каждая строка учитывается своим знаком БЕЗ исключений,
        # включая строки комиссии СБП (они реально списываются со счёта).
        # bank_commission_total - вся распознанная комиссия (оба способа из
        # комментария выше), которая при этом была вычтена из raw одним из двух
        # путей: у классического эквайринга - "невидимо", она вообще не пришла
        # отдельной строкой (просто зачисление меньше на её размер), у СБП -
        # "видимо", отдельной строкой -amount. В обоих случаях raw оказывается
        # МЕНЬШЕ валовой суммы продажи ровно на размер комиссии, поэтому чтобы
        # получить сумму, сравнимую с ВАЛОВОЙ выручкой чеков, комиссия
        # добавляется обратно один раз: bank_total = bank_raw_total + bank_commission_total.
        for (op_date, amount, direction, purpose, commission_amount, commission_source,
             acquiring_commission_text, qr_id, is_sbp_commission_row) in bank_rows:
            amount_f = float(amount) if amount else 0.0
            is_in = direction == 'in'
            signed_amount = amount_f if is_in else -amount_f
            bank_raw_total += signed_amount
            bank_count += 1

            commission_f = 0.0
            if is_in and commission_amount and float(commission_amount) > 0:
                commission_f = float(commission_amount)
                if commission_source in ('registry', 'purpose'):
                    bank_with_known_commission += 1
            elif is_in and acquiring_commission_text:
                # (а) классический эквайринг - сумма комиссии написана в purpose
                # самого зачисления, банк её уже вычел до зачисления "невидимо".
                commission_f = float(acquiring_commission_text.replace(',', '.'))
                bank_with_known_commission += 1
            elif direction == 'out' and is_sbp_commission_row:
                # (б) СБП - сама строка комиссии, уже вычтена из raw выше как
                # обычный расход (-amount) - распознаём её отдельно только для
                # подсчёта bank_commission_total (добавить обратно) и счётчика.
                commission_f = amount_f
                bank_with_known_commission += 1

            bank_commission_total += commission_f
            if op_date:
                day_key = op_date.isoformat()
                daily_bank[day_key] = daily_bank.get(day_key, 0.0) + signed_amount + commission_f
                daily_commission[day_key] = daily_commission.get(day_key, 0.0) + commission_f

        bank_total = bank_raw_total + bank_commission_total

        # Единая ось дат для графика - каждый день периода, даже если по нему
        # нет данных ни по одной из трёх точек (столбец останется нулевым).
        daily = []
        cursor_date = date_from
        while cursor_date <= date_to:
            day_key = cursor_date.isoformat()
            daily.append({
                'date': day_key,
                'payments': round(daily_payments.get(day_key, 0.0), 2),
                'receipts': round(daily_receipts.get(day_key, 0.0), 2),
                'receipts_ofd': round(daily_receipts_ofd.get(day_key, 0.0), 2),
                'bank': round(daily_bank.get(day_key, 0.0), 2),
                'commission': round(daily_commission.get(day_key, 0.0), 2)
            })
            cursor_date += timedelta(days=1)

        payments_by_provider_rounded = {
            provider: {'amount': round(data['amount'], 2), 'count': data['count']}
            for provider, data in payments_by_provider.items()
        }

        details = {
            'payments_by_status': payments_by_status,
            'payments_by_provider': payments_by_provider_rounded,
            'receipts_ofd_total': round(receipts_ofd_total, 2),
            'receipts_ofd_count': receipts_ofd_count,
            'advance_offset_total': round(advance_offset_total, 2),
            'advance_offset_count': advance_offset_count,
            'bank_transactions_total': bank_count,
            'bank_transactions_with_registry_commission': bank_with_known_commission,
            'bank_commission_note': (
                'Комиссия эквайринга неизвестна ни по одной операции - суммы банка '
                'взяты как есть из выписки, без учёта комиссии. Подключите реестр '
                'платежей терминала эквайринга или проверьте, что банк указывает '
                'сумму комиссии в назначении платежа.'
                if bank_with_known_commission == 0 and bank_count > 0 else None
            )
        }

        payments_total = round(payments_total, 2)
        receipts_total = round(receipts_total, 2)
        bank_raw_total = round(bank_raw_total, 2)
        bank_commission_total = round(bank_commission_total, 2)
        bank_total = round(bank_total, 2)

        cur.execute(f'''
            INSERT INTO {SCHEMA}.reconciliation_snapshots (
                company_id, period_from, period_to,
                payments_total, payments_count,
                receipts_total, receipts_count,
                bank_raw_total, bank_commission_total, bank_total, bank_count,
                details, calculated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (company_id, period_from, period_to) DO UPDATE SET
                payments_total = EXCLUDED.payments_total,
                payments_count = EXCLUDED.payments_count,
                receipts_total = EXCLUDED.receipts_total,
                receipts_count = EXCLUDED.receipts_count,
                bank_raw_total = EXCLUDED.bank_raw_total,
                bank_commission_total = EXCLUDED.bank_commission_total,
                bank_total = EXCLUDED.bank_total,
                bank_count = EXCLUDED.bank_count,
                details = EXCLUDED.details,
                calculated_at = NOW()
        ''', (
            company_id, date_from, date_to,
            payments_total, payments_count,
            receipts_total, receipts_count,
            bank_raw_total, bank_commission_total, bank_total, bank_count,
            json.dumps(details)
        ))
        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'period': {'date_from': date_from.isoformat(), 'date_to': date_to.isoformat()},
                'totals': {
                    'payments': {'amount': payments_total, 'count': payments_count},
                    'receipts': {
                        'amount': receipts_total,
                        'count': receipts_count,
                        'ofd_amount': round(receipts_ofd_total, 2),
                        'ofd_count': receipts_ofd_count
                    },
                    'bank': {
                        'amount': bank_total,
                        'raw_amount': bank_raw_total,
                        'commission_amount': bank_commission_total,
                        'count': bank_count
                    }
                },
                'daily': daily,
                'details': details
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
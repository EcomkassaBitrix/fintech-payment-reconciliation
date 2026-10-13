import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

SCHEMA = 't_p83864310_fintech_payment_reco'

SETTLEMENT_DATE_RE = re.compile(r'за\s+(\d{2}\.\d{2}\.\d{4})')
COMMISSION_RE = re.compile(r'сумма комиссии\s+([\d\s]+(?:[.,]\d{1,2})?)\s*руб', re.IGNORECASE)


def parse_settlement(purpose: str):
    '''Из назначения зачисления эквайринга достаёт дату продаж ("за ДД.ММ.ГГГГ") и комиссию.'''
    if not purpose:
        return None, None
    date_m = SETTLEMENT_DATE_RE.search(purpose)
    comm_m = COMMISSION_RE.search(purpose)
    if not date_m or not comm_m:
        return None, None
    try:
        settlement_date = datetime.strptime(date_m.group(1), '%d.%m.%Y').date()
    except ValueError:
        return None, None
    commission = Decimal(comm_m.group(1).replace(' ', '').replace(',', '.'))
    return settlement_date, commission


# Выплаты рассрочек (Долями, Сплит, Подели и т.п.): приходят позже одной суммой за вычетом
# вознаграждения. Пример Долями (ООО «Т-Покупки»): «...по Реестру переводов №4460124 от 2026-10-12
# (pay_in_4), Сумма Вознаграждения 1583-49...». От каких контрагентов брать - настройка банка
# bnpl_counterparties (ИНН или часть названия через запятую); не задана - только Т-Покупки.
DEFAULT_BNPL_COUNTERPARTIES = '7743414212'
# Как в платежах называются способы оплаты рассрочкой.
BNPL_PAYMENT_MARKERS = ('dolyame', 'долями', 'рассроч', 'installment', 'split', 'сплит', 'podeli', 'подели',
                        'mokka', 'мокка', 'plait', 'плайт', 'bnpl', 'pay_in_4')
# Регулярка для базы: lower()/ILIKE базы не меняют регистр русских букв - перечисляем варианты.
BNPL_PAYMENT_PATTERN = '|'.join(sorted({v for m in BNPL_PAYMENT_MARKERS for v in (m, m.capitalize(), m.upper())}))
BNPL_REGISTRY_RE = re.compile(r'Реестр\w*\s+(?:переводов|платежей|операций)?\s*№\s*([\w-]+)\s+от\s+(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})', re.IGNORECASE)
BNPL_DATE_RE = re.compile(r'\bза\s+(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})', re.IGNORECASE)
BNPL_FEE_RE = re.compile(r'(?:вознаграждени\w*|комисси\w*|удержан\w*)\D{0,25}?(\d[\d\s]*)(?:[-.,](\d{1,2}))?\s*(?:руб|р\.|₽|,|\.|$|\s)',
                         re.IGNORECASE)
# Платежи ищем за несколько дней до даты реестра (реестр формируют на следующий день).
BNPL_LOOKBACK_DAYS = 3


def bnpl_counterparties(config: Optional[dict]) -> list:
    raw = (config or {}).get('bnpl_counterparties')
    if raw is None:
        raw = DEFAULT_BNPL_COUNTERPARTIES
    return [w.strip().lower() for w in str(raw).split(',') if w.strip()]


def is_bnpl_counterparty(filters: list, inn: Optional[str], name: Optional[str]) -> bool:
    inn = re.sub(r'\D', '', inn or '')
    name = (name or '').lower()
    for f in filters:
        digits = re.sub(r'\D', '', f)
        if digits and digits == f.replace(' ', ''):
            if inn and inn == digits:
                return True
        elif f in name:
            return True
    return False


def _parse_date(raw: str):
    try:
        return datetime.strptime(raw, '%Y-%m-%d' if '-' in raw else '%d.%m.%Y').date()
    except ValueError:
        return None


def parse_bnpl(purpose: str, operation_date=None):
    '''Выплата рассрочки: (день продаж, вознаграждение, номер реестра) или (None, None, None).'''
    text = purpose or ''
    fee_m = BNPL_FEE_RE.search(text)
    if not fee_m:
        return None, None, None
    reg_m = BNPL_REGISTRY_RE.search(text)
    day, registry_no = None, None
    if reg_m:
        day, registry_no = _parse_date(reg_m.group(2)), reg_m.group(1)
    else:
        date_m = BNPL_DATE_RE.search(text)
        if date_m:
            day = _parse_date(date_m.group(1))
    if not day and operation_date:
        # Даты в назначении нет - продажи накануне поступления.
        day = (operation_date.date() if hasattr(operation_date, 'date') else operation_date) - timedelta(days=1)
    if not day:
        return None, None, None
    rub = fee_m.group(1).replace(' ', '')
    kop = (fee_m.group(2) or '0').ljust(2, '0')
    return day, Decimal(f'{rub}.{kop}'), registry_no


def find_bnpl_payments(cur, company_id: int, registry_date) -> list:
    '''Успешные платежи рассрочкой компании за несколько дней до даты реестра (включительно), ещё не привязанные.'''
    cur.execute(f'''
        WITH latest AS (
            SELECT DISTINCT ON (wp.integration_id, wp.payment_id)
                wp.id, wp.amount, wp.status, wp.payment_provider,
                COALESCE(er.doc_datetime, wp.created_at)::date AS pay_date
            FROM {SCHEMA}.webhook_payments wp
            JOIN {SCHEMA}.user_integrations ui ON ui.id = wp.integration_id
            LEFT JOIN {SCHEMA}.ecomkassa_receipts er ON er.id = wp.receipt_id
            WHERE wp.company_id = %s AND wp.removed_at IS NULL AND ui.status = 'active'
            ORDER BY wp.integration_id, wp.payment_id, wp.created_at DESC
        )
        SELECT l.id, l.amount, l.pay_date FROM latest l
        WHERE l.pay_date BETWEEN %s::date - %s AND %s::date
          AND l.status IN ('AUTHORIZED', 'CONFIRMED')
          AND COALESCE(l.payment_provider, '') ~ %s
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.bank_statement_transactions b
                          WHERE b.linked_payment_id = l.id AND b.removed_at IS NULL)
        ORDER BY l.pay_date DESC, l.id
    ''', (company_id, registry_date, BNPL_LOOKBACK_DAYS, registry_date, BNPL_PAYMENT_PATTERN))
    return cur.fetchall()


def _pick_bnpl(payments: list, gross: Decimal, registry_date) -> list:
    '''Один платёж на всю сумму (ближайший к дате реестра), иначе все платежи дня реестра или накануне, если сумма сходится.'''
    single = [p for p in payments if abs(Decimal(str(p[1])) - gross) < Decimal('0.01')]
    if single:
        return [single[0]]
    by_day: dict = {}
    for p in payments:
        by_day.setdefault(p[2], []).append(p)
    for day in sorted(by_day, key=lambda d: abs((registry_date - d).days)):
        if abs(sum(Decimal(str(p[1])) for p in by_day[day]) - gross) < Decimal('0.01'):
            return by_day[day]
    return []


def _link_group(cur, company_id: int, provider_slug: str, dep_id: int, payment_ids: list) -> None:
    '''Зачисление и несколько платежей - одна группа через общую таблицу связей.'''
    group_id = f'00000000-0000-4000-8000-{dep_id:012d}'
    members = [('money', provider_slug, dep_id)]
    for pay_id in payment_ids:
        cur.execute(f'''
            SELECT p.slug FROM {SCHEMA}.webhook_payments wp
            JOIN {SCHEMA}.user_integrations ui ON ui.id = wp.integration_id
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            WHERE wp.id = %s
        ''', (pay_id,))
        row = cur.fetchone()
        if row:
            members.append(('payment', row[0], pay_id))
    for tx_type, tx_source, tx_id in members:
        cur.execute(f'''
            INSERT INTO {SCHEMA}.manual_transaction_links
                (company_id, link_group_id, tx_type, tx_source, tx_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (company_id, tx_type, tx_source, tx_id) DO NOTHING
        ''', (company_id, group_id, tx_type, tx_source, tx_id))


def _commission_row(cur, integration_id: int, company_id: int, provider_slug: str, dep_id: int, ext_id: str,
                    op_date, commission: Decimal, settlement_date, title: str, purpose: str) -> bool:
    cur.execute(f'''
        INSERT INTO {SCHEMA}.bank_statement_transactions (
            integration_id, company_id, provider_slug, external_transaction_id,
            operation_date, amount, direction, counterparty_name, purpose,
            parent_transaction_id, settlement_date, commission_amount, commission_source, origin
        ) VALUES (%s, %s, %s, %s, %s, %s, 'out', %s, %s, %s, %s, %s, 'purpose', 'sync')
        ON CONFLICT (integration_id, external_transaction_id) DO NOTHING
        RETURNING id
    ''', (integration_id, company_id, provider_slug, f'{ext_id}:commission', op_date, commission, title,
          purpose, dep_id, settlement_date, commission))
    return cur.fetchone() is not None


def process_bnpl_settlements(cur, integration_id: int, company_id: int, provider_slug: str,
                             config: Optional[dict] = None) -> int:
    '''
    Выплаты рассрочек от контрагентов из настройки банка (bnpl_counterparties). Как у эквайринга:
    день продаж = дата реестра (или «за дату», иначе накануне поступления), расчётная строка
    вознаграждения в группе, связь с платежом(ами) рассрочкой, только если зачисление +
    вознаграждение = сумма платежей. Returns: число новых строк вознаграждения.
    '''
    filters = bnpl_counterparties(config)
    if not filters:
        return 0
    cur.execute(f'''
        SELECT id, external_transaction_id, operation_date, amount, purpose, counterparty_inn, counterparty_name,
               linked_payment_id
        FROM {SCHEMA}.bank_statement_transactions
        WHERE integration_id = %s AND company_id = %s
          AND direction = 'in' AND removed_at IS NULL AND parent_transaction_id IS NULL
    ''', (integration_id, company_id))
    created = 0
    for dep_id, ext_id, op_date, amount, purpose, inn, name, linked_payment_id in cur.fetchall():
        if not is_bnpl_counterparty(filters, inn, name):
            continue
        day, fee, registry_no = parse_bnpl(purpose or '', op_date)
        if not day or fee is None:
            continue
        short = re.sub(r'\s+', ' ', re.sub(r'(?i)общество с ограниченной ответственностью|ооо|ао|пао|["«»]', ' ', name or '')).strip()
        source = 'Долями' if re.sub(r'\D', '', inn or '') == DEFAULT_BNPL_COUNTERPARTIES else (short or 'рассрочки')
        cur.execute(f'''
            UPDATE {SCHEMA}.bank_statement_transactions
            SET settlement_date = %s, commission_amount = %s, commission_source = 'purpose',
                purpose_category = 'bnpl_payout'
            WHERE id = %s
        ''', (day, fee, dep_id))
        registry = f'по реестру №{registry_no} ' if registry_no else ''
        if _commission_row(cur, integration_id, company_id, provider_slug, dep_id, ext_id, op_date, fee, day,
                           f'Вознаграждение {source}'[:255],
                           f'Вознаграждение «{source}» {registry}за {day.strftime("%d.%m.%Y")} '
                           f'(удержано из зачисления {amount} руб.)'):
            created += 1
        if linked_payment_id:
            continue
        gross = Decimal(str(amount)) + fee
        chosen = _pick_bnpl(find_bnpl_payments(cur, company_id, day), gross, day)
        if not chosen:
            continue
        cur.execute(f'UPDATE {SCHEMA}.bank_statement_transactions SET linked_payment_id = %s WHERE id = %s',
                    (chosen[0][0], dep_id))
        if len(chosen) > 1:
            _link_group(cur, company_id, provider_slug, dep_id, [p[0] for p in chosen])
    return created


def find_card_payments(cur, company_id: int, settlement_date) -> list:
    '''
    Успешные карточные (не СБП) платежи компании за день продаж. Дата платежа -
    дата пробитого чека, если он привязан, иначе дата вебхука (как в сверке).
    '''
    cur.execute(f'''
        WITH latest AS (
            SELECT DISTINCT ON (wp.integration_id, wp.payment_id)
                wp.id, wp.amount, wp.status, wp.payment_provider,
                COALESCE(er.doc_datetime, wp.created_at)::date AS pay_date
            FROM {SCHEMA}.webhook_payments wp
            JOIN {SCHEMA}.user_integrations ui ON ui.id = wp.integration_id
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            JOIN {SCHEMA}.integration_categories c ON c.id = p.category_id
            LEFT JOIN {SCHEMA}.ecomkassa_receipts er ON er.id = wp.receipt_id
            WHERE wp.company_id = %s AND c.slug = 'payments'
              AND wp.removed_at IS NULL AND ui.status = 'active'
            ORDER BY wp.integration_id, wp.payment_id, wp.created_at DESC
        )
        SELECT id, amount FROM latest
        WHERE pay_date = %s
          AND status IN ('AUTHORIZED', 'CONFIRMED')
          AND COALESCE(payment_provider, '') NOT ILIKE '%%SBP%%'
          AND COALESCE(payment_provider, '') !~ %s
        ORDER BY id
    ''', (company_id, settlement_date, BNPL_PAYMENT_PATTERN))
    return cur.fetchall()


def process_acquiring_settlements(cur, integration_id: int, company_id: int, provider_slug: str,
                                  config: Optional[dict] = None) -> int:
    '''
    Зачисление классического эквайринга приходит на следующий день(и) одной
    суммой за весь день продаж, уже за вычетом комиссии, а в назначении банк
    пишет "за ДД.ММ.ГГГГ" и "Справочно: сумма комиссии X руб". Для каждого
    такого зачисления:
    1) проставляем settlement_date - день продаж, к которому относятся деньги
       (сверка считает их за этот день, а не за день поступления);
    2) создаём отдельную строку комиссии (direction='out', parent_transaction_id
       = зачисление) - чтобы в группе транзакций было видно: платёж 2500 =
       зачисление 2420 + комиссия 80. Это расчётная строка, реального списания
       со счёта нет, поэтому сверка её не суммирует (см. reconciliation-stats);
    3) привязываем зачисление к карточным платежам того дня, но только если их
       сумма точно равна зачислению + комиссии - иначе связь не ставим, и
       расхождение остаётся видимым.
    Идемпотентно: повторная синхронизация ничего не задваивает.
    Returns: число новых строк комиссии (вместе с выплатами Долями).
    '''
    cur.execute(f'''
        SELECT id, external_transaction_id, operation_date, amount, purpose, linked_payment_id
        FROM {SCHEMA}.bank_statement_transactions
        WHERE integration_id = %s AND company_id = %s
          AND direction = 'in' AND removed_at IS NULL
          AND parent_transaction_id IS NULL
          AND purpose ILIKE '%%умма комиссии%%'
    ''', (integration_id, company_id))
    deposits = cur.fetchall()

    created = 0
    for dep_id, ext_id, op_date, amount, purpose, linked_payment_id in deposits:
        if 'pay_in_4' in (purpose or ''):
            continue
        settlement_date, commission = parse_settlement(purpose or '')
        if not settlement_date or commission is None:
            continue

        cur.execute(f'''
            UPDATE {SCHEMA}.bank_statement_transactions
            SET settlement_date = %s, commission_amount = %s, commission_source = 'purpose'
            WHERE id = %s
        ''', (settlement_date, commission, dep_id))

        cur.execute(f'''
            INSERT INTO {SCHEMA}.bank_statement_transactions (
                integration_id, company_id, provider_slug, external_transaction_id,
                operation_date, amount, direction, counterparty_name, purpose,
                parent_transaction_id, settlement_date, commission_amount, commission_source, origin
            ) VALUES (%s, %s, %s, %s, %s, %s, 'out', %s, %s, %s, %s, %s, 'purpose', 'sync')
            ON CONFLICT (integration_id, external_transaction_id) DO NOTHING
            RETURNING id
        ''', (
            integration_id, company_id, provider_slug, f'{ext_id}:commission',
            op_date, commission, 'Комиссия эквайринга',
            f'Комиссия эквайринга за {settlement_date.strftime("%d.%m.%Y")} (удержана банком из зачисления {amount} руб.)',
            dep_id, settlement_date, commission
        ))
        if cur.fetchone():
            created += 1

        if linked_payment_id:
            continue

        payments = find_card_payments(cur, company_id, settlement_date)
        if not payments:
            continue
        gross = Decimal(str(amount)) + commission
        payments_sum = sum(Decimal(str(a)) for _, a in payments)
        if abs(payments_sum - gross) >= Decimal('0.01'):
            continue

        cur.execute(f'''
            UPDATE {SCHEMA}.bank_statement_transactions
            SET linked_payment_id = %s
            WHERE id = %s
        ''', (payments[0][0], dep_id))

        # Остальные платежи того же дня (если их несколько) объединяем с
        # зачислением в одну группу через общую таблицу связей.
        if len(payments) > 1:
            group_id = f'00000000-0000-4000-8000-{dep_id:012d}'
            members = [('money', provider_slug, dep_id)]
            for pay_id, _ in payments:
                cur.execute(f'''
                    SELECT p.slug FROM {SCHEMA}.webhook_payments wp
                    JOIN {SCHEMA}.user_integrations ui ON ui.id = wp.integration_id
                    JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
                    WHERE wp.id = %s
                ''', (pay_id,))
                row = cur.fetchone()
                if row:
                    members.append(('payment', row[0], pay_id))
            for tx_type, tx_source, tx_id in members:
                cur.execute(f'''
                    INSERT INTO {SCHEMA}.manual_transaction_links
                        (company_id, link_group_id, tx_type, tx_source, tx_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (company_id, tx_type, tx_source, tx_id) DO NOTHING
                ''', (company_id, group_id, tx_type, tx_source, tx_id))

    return created + process_bnpl_settlements(cur, integration_id, company_id, provider_slug, config)

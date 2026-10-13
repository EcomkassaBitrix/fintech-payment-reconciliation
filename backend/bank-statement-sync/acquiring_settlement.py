import re
from datetime import datetime
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


# Выплаты «Долями» (ООО «Т-Покупки»): «...по Реестру переводов №4460124 от 2026-10-12 (pay_in_4),
# Сумма Вознаграждения 1583-49...» - деньги приходят на следующий день за вычетом вознаграждения.
BNPL_INNS = ('7743414212',)
BNPL_REGISTRY_RE = re.compile(r'Реестр\w*\s+переводов\s+№\s*(\d+)\s+от\s+(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})', re.IGNORECASE)
BNPL_FEE_RE = re.compile(r'Сумм\w*\s+вознаграждения\s+(\d[\d\s]*)(?:[-.,](\d{1,2}))?', re.IGNORECASE)
# Платежи Долями ищем за несколько дней до даты реестра (реестр формируют на следующий день).
BNPL_LOOKBACK_DAYS = 3


def parse_bnpl(purpose: str, counterparty_inn: Optional[str]):
    '''Выплата Долями: (дата реестра, вознаграждение, номер реестра) или (None, None, None).'''
    text = purpose or ''
    if not ((counterparty_inn or '') in BNPL_INNS or 'pay_in_4' in text):
        return None, None, None
    reg_m = BNPL_REGISTRY_RE.search(text)
    fee_m = BNPL_FEE_RE.search(text)
    if not reg_m or not fee_m:
        return None, None, None
    raw_date = reg_m.group(2)
    try:
        registry_date = datetime.strptime(raw_date, '%Y-%m-%d' if '-' in raw_date else '%d.%m.%Y').date()
    except ValueError:
        return None, None, None
    rub = fee_m.group(1).replace(' ', '')
    kop = (fee_m.group(2) or '0').ljust(2, '0')
    return registry_date, Decimal(f'{rub}.{kop}'), reg_m.group(1)


def find_bnpl_payments(cur, company_id: int, registry_date) -> list:
    '''Успешные платежи Долями компании за несколько дней до даты реестра (включительно), ещё не привязанные.'''
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
          AND (l.payment_provider ILIKE '%%DOLYAME%%' OR l.payment_provider ILIKE '%%Долями%%')
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.bank_statement_transactions b
                          WHERE b.linked_payment_id = l.id AND b.removed_at IS NULL)
        ORDER BY l.pay_date DESC, l.id
    ''', (company_id, registry_date, BNPL_LOOKBACK_DAYS, registry_date))
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


def process_bnpl_settlements(cur, integration_id: int, company_id: int, provider_slug: str) -> int:
    '''
    Выплаты «Долями» (ООО «Т-Покупки»): приходят на следующий день за вычетом вознаграждения.
    Как у эквайринга: день продаж = дата реестра, расчётная строка вознаграждения в группе,
    связь с платежом(ами) Долями, только если зачисление + вознаграждение = сумма платежей.
    Returns: число новых строк вознаграждения.
    '''
    cur.execute(f'''
        SELECT id, external_transaction_id, operation_date, amount, purpose, counterparty_inn, linked_payment_id
        FROM {SCHEMA}.bank_statement_transactions
        WHERE integration_id = %s AND company_id = %s
          AND direction = 'in' AND removed_at IS NULL AND parent_transaction_id IS NULL
          AND (counterparty_inn = ANY(%s) OR purpose ILIKE '%%pay_in_4%%')
    ''', (integration_id, company_id, list(BNPL_INNS)))
    # Текст назначения проверяем в parse_bnpl: ILIKE базы не сравнивает русские буквы без учёта регистра.
    created = 0
    for dep_id, ext_id, op_date, amount, purpose, inn, linked_payment_id in cur.fetchall():
        registry_date, fee, registry_no = parse_bnpl(purpose or '', inn)
        if not registry_date or fee is None:
            continue
        cur.execute(f'''
            UPDATE {SCHEMA}.bank_statement_transactions
            SET settlement_date = %s, commission_amount = %s, commission_source = 'purpose',
                purpose_category = COALESCE(purpose_category, 'bnpl_payout')
            WHERE id = %s
        ''', (registry_date, fee, dep_id))
        if _commission_row(cur, integration_id, company_id, provider_slug, dep_id, ext_id, op_date, fee, registry_date,
                           'Вознаграждение Долями',
                           f'Вознаграждение «Долями» по реестру №{registry_no} от {registry_date.strftime("%d.%m.%Y")} '
                           f'(удержано из зачисления {amount} руб.)'):
            created += 1
        if linked_payment_id:
            continue
        gross = Decimal(str(amount)) + fee
        chosen = _pick_bnpl(find_bnpl_payments(cur, company_id, registry_date), gross, registry_date)
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
          AND COALESCE(payment_provider, '') NOT ILIKE '%%DOLYAME%%'
          AND COALESCE(payment_provider, '') NOT ILIKE '%%Долями%%'
        ORDER BY id
    ''', (company_id, settlement_date))
    return cur.fetchall()


def process_acquiring_settlements(cur, integration_id: int, company_id: int, provider_slug: str) -> int:
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

    return created + process_bnpl_settlements(cur, integration_id, company_id, provider_slug)

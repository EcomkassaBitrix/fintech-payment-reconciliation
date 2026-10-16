import json
import re
import time
from typing import Any, Dict, List, Optional

import downgrade
import tbank_billing

SCHEMA = 't_p83864310_fintech_payment_reco'
FAILED_STATUSES = ('REJECTED', 'DEADLINE_EXPIRED', 'AUTH_FAIL', 'ATTEMPTS_EXPIRED')
CANCELED_STATUSES = ('CANCELED', 'REVERSED')
REFUND_STATUSES = ('REFUNDED', 'PARTIAL_REFUNDED')
NOTIFY_COMPANIES: List[int] = []


def _amount(pay: Dict[str, Any]) -> str:
    return f"{float(pay['amount']):,.2f}".replace(',', ' ').replace('.', ',')


def _notify(cur, pay: Dict[str, Any], kind: str, level: str, title: str, message: str) -> None:
    '''Уведомление по платежу подписки: в кабинет и в выбранный сотрудником канал (один раз на платёж).'''
    cur.execute(f'''
        INSERT INTO {SCHEMA}.notifications (company_id, kind, level, title, message, link_module, entity_type, entity_id, payload)
        SELECT %s, %s, %s, %s, %s, 'subscription', 'subscription_payment', %s, %s
        WHERE NOT EXISTS (SELECT 1 FROM {SCHEMA}.notifications
                          WHERE kind = %s AND entity_type = 'subscription_payment' AND entity_id = %s)
        RETURNING id
    ''', (pay['company_id'], kind, level, title, message, str(pay['id']),
          json.dumps({'payment_id': pay['id'], 'amount': float(pay['amount'])}), kind, str(pay['id'])))
    row = cur.fetchone()
    if not row:
        return
    cur.execute(f'''
        INSERT INTO {SCHEMA}.notification_deliveries (notification_id, user_id, channel)
        SELECT %s, p.user_id, p.channel
        FROM {SCHEMA}.notification_preferences p
        JOIN {SCHEMA}.company_users cu ON cu.company_id = p.company_id AND cu.user_id = p.user_id AND cu.status = 'active'
        WHERE p.company_id = %s AND p.channel IS NOT NULL
        ON CONFLICT (notification_id, user_id) DO NOTHING
    ''', (row[0], pay['company_id']))
    NOTIFY_COMPANIES.append(pay['company_id'])


def notify_paid(cur, pay: Dict[str, Any], period_end) -> None:
    if pay.get('is_test'):
        return
    until = period_end.strftime('%d.%m.%Y') if hasattr(period_end, 'strftime') else str(period_end)[:10]
    how = 'Автопродление: списано' if pay.get('is_recurring') else 'Оплачено'
    _notify(cur, pay, 'subscription_paid', 'success', 'Подписка оплачена',
            f"Тариф «{pay['tariff_name']}». {how} {_amount(pay)} ₽. Подписка действует до {until}.")


def notify_renew_failed(cur, pay: Dict[str, Any], reason: str) -> None:
    if pay.get('is_test') or not pay.get('is_recurring'):
        return
    _notify(cur, pay, 'subscription_renew_failed', 'error', 'Автопродление не прошло',
            f"Тариф «{pay['tariff_name']}», {_amount(pay)} ₽: {reason}. Повторим попытку через 12 часов "
            f"(в течение 3 дней после окончания срока). Пополните карту или оплатите подписку вручную.")


def year_price(price: float, discount: float) -> float:
    return round(price * 12 * (1 - discount / 100), 2)


def load_tariffs(cur) -> List[Dict[str, Any]]:
    cur.execute(f'''
        SELECT id, slug, name, description, price, period_days, yearly_discount_percent,
               modules, max_companies, max_users, max_integrations, max_automations
        FROM {SCHEMA}.tariffs
        WHERE is_active = true AND slug <> 'trial'
        ORDER BY sort_order, id
    ''')
    result = []
    for r in cur.fetchall():
        price, discount = float(r[4]), float(r[6] or 0)
        result.append({
            'id': r[0], 'slug': r[1], 'name': r[2], 'description': r[3],
            'price': price, 'period_days': r[5] or 30, 'yearly_discount_percent': discount,
            'year_price': year_price(price, discount), 'modules': r[7] or [],
            'max_companies': r[8], 'max_users': r[9], 'max_integrations': r[10], 'max_automations': r[11]
        })
    return result


def period_terms(tariff: Dict[str, Any], period: str):
    days = 365 if period == 'year' else int(tariff['period_days'])
    amount = tariff['year_price'] if period == 'year' else tariff['price']
    return days, amount


def activate(cur, company_id: int, tariff_id: int, days: int):
    '''Тот же тариф - продление от даты окончания, другой - новый срок с сегодняшнего дня.'''
    cur.execute(f'SELECT id, tariff_id FROM {SCHEMA}.subscriptions WHERE company_id = %s', (company_id,))
    sub = cur.fetchone()
    if sub and sub[1] == tariff_id:
        cur.execute(f'''
            UPDATE {SCHEMA}.subscriptions SET
                current_period_start = CASE WHEN COALESCE(current_period_end, NOW()) < NOW()
                                            THEN NOW() ELSE current_period_start END,
                current_period_end = GREATEST(COALESCE(current_period_end, NOW()), NOW())
                                     + make_interval(days => %s),
                status = 'active', updated_at = NOW()
            WHERE id = %s RETURNING current_period_end
        ''', (days, sub[0]))
    elif sub:
        cur.execute(f'''
            UPDATE {SCHEMA}.subscriptions SET tariff_id = %s, status = 'active',
                current_period_start = NOW(), current_period_end = NOW() + make_interval(days => %s),
                updated_at = NOW()
            WHERE id = %s RETURNING current_period_end
        ''', (tariff_id, days, sub[0]))
    else:
        cur.execute(f'''
            INSERT INTO {SCHEMA}.subscriptions
                (company_id, tariff_id, status, current_period_start, current_period_end)
            VALUES (%s, %s, 'active', NOW(), NOW() + make_interval(days => %s))
            RETURNING current_period_end
        ''', (company_id, tariff_id, days))
    return cur.fetchone()[0]


def _payer_contacts(cur, user_id):
    cur.execute(f'SELECT phone, email FROM {SCHEMA}.app_users WHERE id = %s', (user_id,))
    r = cur.fetchone()
    return (r[0], r[1]) if r else (None, None)


def _load_payment(cur, where: str, value) -> Optional[Dict[str, Any]]:
    cur.execute(f'''
        SELECT p.id, p.company_id, p.user_id, p.tariff_id, p.period, p.days, p.amount, p.status,
               p.keep_data, p.auto_renew, p.is_recurring, p.provider_payment_id, t.name, p.period_end, p.error_message,
               p.refund_amount, p.is_test
        FROM {SCHEMA}.subscription_payments p JOIN {SCHEMA}.tariffs t ON t.id = p.tariff_id
        WHERE {where} FOR UPDATE OF p
    ''', (value,))
    r = cur.fetchone()
    if not r:
        return None
    keys = ['id', 'company_id', 'user_id', 'tariff_id', 'period', 'days', 'amount', 'status', 'keep',
            'auto_renew', 'is_recurring', 'provider_payment_id', 'tariff_name', 'period_end', 'error', 'refund_amount', 'is_test']
    return dict(zip(keys, r))


def save_card(cur, company_id: int, user_id, data: Dict[str, Any]) -> Optional[int]:
    rebill = str(data.get('RebillId') or '').strip()
    if not rebill:
        return None
    cur.execute(f'''
        UPDATE {SCHEMA}.subscription_cards SET is_active = false, updated_at = NOW()
        WHERE company_id = %s AND is_active = true AND rebill_id <> %s
    ''', (company_id, rebill))
    cur.execute(f'SELECT id FROM {SCHEMA}.subscription_cards WHERE company_id = %s AND rebill_id = %s',
                (company_id, rebill))
    row = cur.fetchone()
    if row:
        cur.execute(f'''UPDATE {SCHEMA}.subscription_cards SET is_active = true, pan = COALESCE(%s, pan),
                        exp_date = COALESCE(%s, exp_date), updated_at = NOW() WHERE id = %s''',
                    (data.get('Pan'), data.get('ExpDate'), row[0]))
        return row[0]
    cur.execute(f'''
        INSERT INTO {SCHEMA}.subscription_cards
            (company_id, provider_slug, rebill_id, card_id, pan, exp_date, customer_key, created_by)
        VALUES (%s, 'tbank', %s, %s, %s, %s, %s, %s) RETURNING id
    ''', (company_id, rebill, str(data.get('CardId') or '') or None, data.get('Pan'), data.get('ExpDate'),
          f'company-{company_id}', user_id))
    return cur.fetchone()[0]


def mark_paid(cur, pay: Dict[str, Any], data: Dict[str, Any]):
    '''Платёж подтверждён: лишнее сверх лимитов убираем, тариф активируем, карту запоминаем.'''
    if pay['status'] == 'paid':
        return pay['period_end']
    tariff = next((t for t in load_tariffs(cur) if t['id'] == pay['tariff_id']), None)
    # Лишнее удаляем ТОЛЬКО по явному выбору клиента на странице тарифа (keep). Тестовые оплаты из админки,
    # автопродления и платежи без выбора данные компании не трогают никогда.
    if tariff and pay['keep'] and not pay.get('is_test') and not pay.get('is_recurring'):
        over = downgrade.overage(cur, pay['company_id'], tariff, pay['user_id'])
        if over:
            removed = downgrade.apply(cur, pay['company_id'], downgrade.to_delete(over, pay['keep'] or {}))
            print(f"downgrade company={pay['company_id']} removed={removed}")
    period_end = activate(cur, pay['company_id'], pay['tariff_id'], pay['days'])
    cur.execute(f'''
        UPDATE {SCHEMA}.subscription_payments SET status = 'paid', period_end = %s, paid_at = NOW(),
            error_message = NULL, updated_at = NOW() WHERE id = %s
    ''', (period_end, pay['id']))
    card_id = save_card(cur, pay['company_id'], pay['user_id'], data)
    if card_id or pay['is_recurring']:
        cur.execute(f'''
            UPDATE {SCHEMA}.subscriptions SET auto_renew = CASE WHEN %s THEN %s ELSE auto_renew END,
                renew_period = %s, card_id = COALESCE(%s, card_id), updated_at = NOW()
            WHERE company_id = %s
        ''', (not pay['is_recurring'], pay['auto_renew'], pay['period'], card_id, pay['company_id']))
    notify_paid(cur, pay, period_end)
    print(f"subscription paid company={pay['company_id']} payment={pay['id']} until={period_end}")
    return period_end


def mark_failed(cur, pay: Dict[str, Any], message: str) -> None:
    if pay['status'] == 'paid':
        return
    cur.execute(f'''UPDATE {SCHEMA}.subscription_payments SET status = 'failed', error_message = %s,
                    updated_at = NOW() WHERE id = %s''', (message[:500], pay['id']))
    notify_renew_failed(cur, pay, message[:300])


def mark_refunded(cur, pay: Dict[str, Any], refunded_kop: Optional[int], partial: bool, user_id=None) -> None:
    amount = round(refunded_kop / 100, 2) if refunded_kop else float(pay['amount'])
    cur.execute(f'''
        UPDATE {SCHEMA}.subscription_payments SET status = %s, refunded_at = COALESCE(refunded_at, NOW()),
            refunded_by = COALESCE(%s, refunded_by), refund_amount = %s, updated_at = NOW() WHERE id = %s
    ''', ('partially_refunded' if partial else 'refunded', user_id, amount, pay['id']))


def mark_canceled(cur, pay: Dict[str, Any], status: str) -> None:
    cur.execute(f'''UPDATE {SCHEMA}.subscription_payments SET status = 'canceled', error_message = %s,
                    updated_at = NOW() WHERE id = %s''', (f'Отменён ({status})', pay['id']))


DECLINE_CODES = {
    '1051': 'Недостаточно средств на карте',
    '1057': 'Банк, выпустивший карту, запретил такую операцию',
    '1054': 'Истёк срок действия карты',
    '1082': 'Неверный CVC или срок действия карты',
    '1089': 'Банк, выпустивший карту, отклонил оплату',
    '1014': 'Неверный номер карты',
    '1013': 'Неверная сумма операции',
    '1019': 'Платёж отклонён по соображениям безопасности',
    '1030': 'Ошибка при оплате — попробуйте ещё раз',
    '1034': 'Не пройдена проверка 3‑D Secure',
    '1041': 'Карта заблокирована',
    '1043': 'Карта заблокирована',
    '1061': 'Превышен лимит по карте',
    '1065': 'Превышен лимит операций по карте',
    '1091': 'Банк, выпустивший карту, недоступен — попробуйте позже',
    '1096': 'Системная ошибка банка — попробуйте позже',
}


def decline_reason(status: str, code: Any) -> str:
    code = str(code or '0')
    if code in DECLINE_CODES:
        return DECLINE_CODES[code]
    if status == 'DEADLINE_EXPIRED':
        return 'Время на оплату истекло'
    if status == 'AUTH_FAIL':
        return 'Не пройдена проверка 3‑D Secure'
    if status == 'ATTEMPTS_EXPIRED':
        return 'Превышено число попыток оплаты'
    return 'Банк отклонил оплату' + (f' (код {code})' if code != '0' else '')


def apply_state(cur, pay: Dict[str, Any], data: Dict[str, Any]) -> str:
    status = str(data.get('Status') or '')
    if status == 'CONFIRMED':
        mark_paid(cur, pay, data)
        return 'paid'
    if status in REFUND_STATUSES:
        original, new = data.get('OriginalAmount'), data.get('NewAmount')
        refunded = (int(original) - int(new)) if original is not None and new is not None else None
        mark_refunded(cur, pay, refunded, status == 'PARTIAL_REFUNDED')
        return 'refunded'
    if status in CANCELED_STATUSES and pay['status'] != 'paid':
        mark_canceled(cur, pay, status)
        return 'canceled'
    if status in FAILED_STATUSES:
        mark_failed(cur, pay, decline_reason(status, data.get('ErrorCode')))
        return 'failed'
    return pay['status']


def receipt_title(tariff: Dict[str, Any], period: str, days: int) -> str:
    term = '12 мес.' if period == 'year' else ('1 мес.' if days in (30, 31) else f'{days} дн.')
    return f"Подписка на сервис «Сверка», тариф «{tariff['name']}», {term}"


def create_payment(cur, company_id, user_id, tariff, period, *, keep=None, auto_renew=False, recurring=False,
                   is_test=False) -> Dict[str, Any]:
    days, amount = period_terms(tariff, period)
    cur.execute(f'''
        INSERT INTO {SCHEMA}.subscription_payments
            (company_id, user_id, tariff_id, period, days, amount, status, method, provider_slug,
             keep_data, auto_renew, is_recurring, is_test)
        VALUES (%s, %s, %s, %s, %s, %s, 'pending', 'tbank', 'tbank', %s, %s, %s, %s) RETURNING id
    ''', (company_id, user_id, tariff['id'], period, days, amount,
          json.dumps(keep) if keep else None, auto_renew, recurring, is_test))
    pay_id = cur.fetchone()[0]
    order_id = f'sv{pay_id}-{int(time.time())}'
    cur.execute(f'UPDATE {SCHEMA}.subscription_payments SET order_id = %s WHERE id = %s', (order_id, pay_id))
    return {'id': pay_id, 'order_id': order_id, 'amount': amount, 'days': days}


ALLOWED_RETURN = re.compile(r'^https://([a-z0-9-]+\.)*(s-verka\.ru|poehali\.dev|poehali\.app|preview\.poehali\.dev)(:\d+)?$')


def return_base(origin: Optional[str]) -> str:
    '''Адрес возврата с платёжной формы - сайт, с которого начали оплату (редактор, превью или боевой).'''
    origin = (origin or '').strip().rstrip('/')
    return origin if origin and ALLOWED_RETURN.match(origin) else tbank_billing.SITE_URL


def start_checkout(cur, terminal, company_id, user_id, tariff, period, keep, auto_renew, is_test=False,
                   save_card: bool = True, origin: Optional[str] = None) -> Dict[str, Any]:
    '''Первый платёж с сохранением карты: ссылка на платёжную форму Т‑Банка.'''
    p = create_payment(cur, company_id, user_id, tariff, period, keep=keep, auto_renew=auto_renew, is_test=is_test)
    phone, email = _payer_contacts(cur, user_id)
    base = return_base(origin)
    back = (f"{base}/admin?section=payments&tp={p['id']}" if is_test
            else f"{base}/app?section=subscription&sp={p['id']}")
    data, err = tbank_billing.init_payment(
        terminal, order_id=p['order_id'], amount_kop=int(round(p['amount'] * 100)),
        description=f"Подписка «{tariff['name']}» на {p['days']} дн.", customer_key=f'company-{company_id}',
        receipt_title=receipt_title(tariff, period, p['days']),
        recurrent_first=save_card, plain_sale=not save_card, phone=phone, email=email, success_url=back, fail_url=back)
    if err or not data or not data.get('PaymentURL'):
        cur.execute(f'''UPDATE {SCHEMA}.subscription_payments SET status = 'failed', error_message = %s,
                        updated_at = NOW() WHERE id = %s''', ((err or 'Т‑Банк не выдал ссылку на оплату')[:500], p['id']))
        return {'success': False, 'error': err or 'Т‑Банк не выдал ссылку на оплату'}
    cur.execute(f'''UPDATE {SCHEMA}.subscription_payments SET provider_payment_id = %s, payment_url = %s,
                    updated_at = NOW() WHERE id = %s''', (str(data.get('PaymentId')), data['PaymentURL'], p['id']))
    return {'success': True, 'payment_url': data['PaymentURL'], 'payment_id': p['id']}


def handle_notification(cur, data: Dict[str, Any]) -> bool:
    '''Уведомление Т‑Банка о статусе платежа подписки. False - подпись не сошлась.'''
    terminal = tbank_billing.terminal_by_key(cur, str(data.get('TerminalKey') or ''))
    if not terminal or not tbank_billing.verify(data, terminal['password']):
        print(f"[tbank-notify] bad token or no terminal order={data.get('OrderId')}")
        return False
    pay = _load_payment(cur, 'p.order_id = %s', str(data.get('OrderId') or ''))
    if not pay:
        print(f"[tbank-notify] unknown order {data.get('OrderId')}")
        return True
    if not pay['provider_payment_id'] and data.get('PaymentId'):
        cur.execute(f'UPDATE {SCHEMA}.subscription_payments SET provider_payment_id = %s WHERE id = %s',
                    (str(data['PaymentId']), pay['id']))
    print(f"[tbank-notify] payment={pay['id']} status={data.get('Status')} rebill={bool(data.get('RebillId'))}")
    apply_state(cur, pay, data)
    return True


def refresh(cur, company_id: int, payment_id: int) -> Optional[Dict[str, Any]]:
    '''Возврат с платёжной формы: если уведомление ещё не пришло - спрашиваем статус у банка.'''
    pay = _load_payment(cur, 'p.id = %s', payment_id)
    if not pay or pay['company_id'] != int(company_id):
        return None
    if pay['status'] == 'pending' and pay['provider_payment_id']:
        terminal = tbank_billing.load_terminal(cur, only_enabled=False, company_id=pay['company_id'])
        if terminal:
            data, _ = tbank_billing.get_state(terminal, pay['provider_payment_id'])
            if data and data.get('Success'):
                apply_state(cur, pay, data)
                pay = _load_payment(cur, 'p.id = %s', payment_id)
    cur.execute(f'''
        SELECT p.refund_amount, p.is_recurring,
               EXISTS (SELECT 1 FROM {SCHEMA}.subscription_cards c WHERE c.company_id = p.company_id AND c.is_active = true
                       AND c.created_at >= p.created_at - INTERVAL '1 minute')
        FROM {SCHEMA}.subscription_payments p WHERE p.id = %s
    ''', (pay['id'],))
    extra = cur.fetchone() or (None, False, False)
    return {'id': pay['id'], 'status': pay['status'], 'tariff_name': pay['tariff_name'],
            'period_end': pay['period_end'], 'amount': float(pay['amount']), 'error': pay['error'],
            'refund_amount': float(extra[0]) if extra[0] is not None else None, 'is_recurring': extra[1],
            'card_saved': bool(extra[2]) and pay['status'] == 'paid'}


def cancel_payment(cur, terminal, payment_id: int, user_id=None, amount: Optional[float] = None) -> Dict[str, Any]:
    '''
    Отмена неоплаченного платежа или возврат оплаченного (полный или частичный) через Cancel.
    Частичный возврат при включённой кассе - с чеком на возвращаемую сумму.
    '''
    pay = _load_payment(cur, 'p.id = %s', payment_id)
    if not pay or not pay['provider_payment_id']:
        return {'success': False, 'error': 'Платёж не найден в Т‑Банке'}
    if pay['status'] in ('refunded', 'canceled'):
        return {'success': False, 'error': 'Платёж уже отменён или возвращён'}
    total_kop = int(round(float(pay['amount']) * 100))
    amount_kop = int(round(amount * 100)) if amount else None
    left_kop = total_kop - int(round(float(pay.get('refund_amount') or 0) * 100))
    if amount_kop and amount_kop > left_kop:
        return {'success': False, 'error': f'Вернуть можно не больше {left_kop / 100} ₽'}
    partial = bool(amount_kop and amount_kop < total_kop)
    rec = None
    if pay['status'] in ('paid', 'partially_refunded'):
        # Чек возврата (тест-кейс №8): передаём позицию на возвращаемую сумму и при полном возврате.
        cur.execute(f'SELECT user_id FROM {SCHEMA}.subscription_payments WHERE id = %s', (payment_id,))
        phone, email = _payer_contacts(cur, cur.fetchone()[0])
        tariff = next((t for t in load_tariffs(cur) if t['id'] == pay['tariff_id']), {'name': pay['tariff_name']})
        refund_kop = amount_kop or (total_kop - int(round(float(pay.get('refund_amount') or 0) * 100)))
        rec = tbank_billing.receipt(terminal, receipt_title(tariff, pay['period'], pay['days']), refund_kop, phone, email)
        amount_kop = refund_kop
    data, err = tbank_billing.cancel(terminal, pay['provider_payment_id'], amount_kop, rec)
    if err or not data:
        return {'success': False, 'error': err or 'Т‑Банк не ответил'}
    status = str(data.get('Status') or '')
    if status in REFUND_STATUSES:
        original, new = data.get('OriginalAmount'), data.get('NewAmount')
        refunded = (int(original) - int(new)) if original is not None and new is not None else amount_kop
        mark_refunded(cur, pay, refunded, status == 'PARTIAL_REFUNDED', user_id)
    elif status in CANCELED_STATUSES:
        mark_canceled(cur, pay, status)
    return {'success': True, 'bank_status': status}


def charge_saved_card(cur, conn, terminal, company_id: int, tariff: Dict[str, Any], period: str, rebill_id: str,
                      payer_id: int, is_test: bool = False) -> Dict[str, Any]:
    '''Списание по сохранённой карте без участия клиента: Init (MIT, R) + Charge с RebillId.'''
    p = create_payment(cur, company_id, payer_id, tariff, period, recurring=True, is_test=is_test)
    conn.commit()
    phone, email = _payer_contacts(cur, payer_id)
    data, err = tbank_billing.init_payment(
        terminal, order_id=p['order_id'], amount_kop=int(round(p['amount'] * 100)),
        description=f"Автопродление подписки «{tariff['name']}» на {p['days']} дн.",
        receipt_title=receipt_title(tariff, period, p['days']),
        customer_key=f'company-{company_id}', recurrent_first=False, phone=phone, email=email)
    pay = _load_payment(cur, 'p.id = %s', p['id'])
    if err or not data:
        mark_failed(cur, pay, err or 'Т‑Банк не создал платёж')
        conn.commit()
        return {'payment_id': p['id'], 'status': 'failed', 'error': err}
    cur.execute(f'UPDATE {SCHEMA}.subscription_payments SET provider_payment_id = %s WHERE id = %s',
                (str(data.get('PaymentId')), p['id']))
    conn.commit()
    result, err = tbank_billing.charge(terminal, str(data.get('PaymentId')), rebill_id)
    pay = _load_payment(cur, 'p.id = %s', p['id'])
    if err and (not result or result.get('Status') != 'CONFIRMED'):
        mark_failed(cur, pay, err)
        status = 'failed'
    else:
        status = apply_state(cur, pay, result or {})
    conn.commit()
    return {'payment_id': p['id'], 'status': status, 'error': err, 'bank_status': (result or {}).get('Status')}


def renew_due(cur, conn, budget_seconds: float = 3.2) -> Dict[str, Any]:
    '''
    Автопродление: подписки с автосписанием, срок которых кончается в ближайшие сутки (или уже
    кончился не больше 3 дней назад), списываем по сохранённой карте. Не чаще одной попытки
    в 12 часов на компанию, чтобы не долбить карту без денег.
    '''
    started = time.time()
    if not tbank_billing.load_terminal(cur):
        return {'skipped': 'terminal', 'renewed': []}
    cur.execute(f'''
        SELECT s.company_id, s.tariff_id, s.renew_period, c.rebill_id,
               (SELECT cu.user_id FROM {SCHEMA}.company_users cu JOIN {SCHEMA}.roles r ON r.id = cu.role_id
                 WHERE cu.company_id = s.company_id AND r.slug = 'owner' AND cu.status = 'active' LIMIT 1)
        FROM {SCHEMA}.subscriptions s
        JOIN {SCHEMA}.subscription_cards c ON c.id = s.card_id AND c.is_active = true
        WHERE s.auto_renew = true
          AND s.current_period_end < NOW() + INTERVAL '1 day'
          AND s.current_period_end > NOW() - INTERVAL '3 days'
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.subscription_payments p
                          WHERE p.company_id = s.company_id AND p.is_recurring = true
                            AND (p.status = 'pending' OR p.created_at > NOW() - INTERVAL '12 hours'))
        ORDER BY s.current_period_end LIMIT 5
    ''')
    due = cur.fetchall()
    tariffs = {t['id']: t for t in load_tariffs(cur)}
    done = []
    for company_id, tariff_id, period, rebill_id, owner_id in due:
        if time.time() - started > budget_seconds:
            break
        tariff = tariffs.get(tariff_id)
        if not tariff or not owner_id:
            continue
        terminal = tbank_billing.load_terminal(cur, company_id=company_id)
        res = charge_saved_card(cur, conn, terminal, company_id, tariff, period or 'month', rebill_id, owner_id)
        status = res['status']
        done.append({'company_id': company_id, 'status': status})
    print(f'[renew_due] {done}')
    # Не всех успели (лимит 5 за раз или время) - планировщик продолжит на следующем запуске.
    more = len(due) == 5 or len(done) < len([d for d in due if tariffs.get(d[1]) and d[4]])
    return {'renewed': done, 'more': more}

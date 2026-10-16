from typing import Any, Dict, Optional, Tuple

import billing

SCHEMA = 't_p83864310_fintech_payment_reco'


def find(cur, code: str, company_id, lock: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    '''Купон по названию и причина, почему его нельзя применить (None - можно).'''
    code = (code or '').strip().upper()
    if not code:
        return None, 'Введите промокод'
    cur.execute(f'''
        SELECT c.id, c.code, c.tariff_id, t.name, c.period, c.usage_type, c.valid_until, c.is_active,
               CASE WHEN c.period = 'year' THEN 365 WHEN c.period = 'half_year' THEN 180 WHEN c.period = 'quarter' THEN 90 ELSE COALESCE(NULLIF(t.period_days, 0), 30) END,
               (c.valid_until < (NOW() AT TIME ZONE 'Europe/Moscow')::date)
        FROM {SCHEMA}.subscription_coupons c JOIN {SCHEMA}.tariffs t ON t.id = c.tariff_id
        WHERE UPPER(c.code) = %s {'FOR UPDATE OF c' if lock else ''}
    ''', (code,))
    r = cur.fetchone()
    if not r:
        return None, 'Такого промокода нет'
    coupon = {'id': r[0], 'code': r[1], 'tariff_id': r[2], 'tariff_name': r[3], 'period': r[4],
              'usage_type': r[5], 'valid_until': r[6].isoformat(), 'days': r[8]}
    if not r[7]:
        return coupon, 'Промокод отключён'
    if r[9]:
        return coupon, 'Срок применения промокода истёк'
    cur.execute(f'''SELECT company_id FROM {SCHEMA}.subscription_coupon_activations WHERE coupon_id = %s''', (r[0],))
    used_by = [row[0] for row in cur.fetchall()]
    if int(company_id) in used_by:
        return coupon, 'Компания уже применила этот промокод'
    if r[5] == 'single' and used_by:
        return coupon, 'Промокод уже использован'
    return coupon, None


def apply(cur, code: str, company_id, user_id) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    '''Начисляет тариф купона: продление того же тарифа или новый срок, запись в истории оплат.'''
    coupon, error = find(cur, code, company_id, lock=True)
    if error:
        return None, error
    period_end = billing.activate(cur, int(company_id), coupon['tariff_id'], coupon['days'])
    cur.execute(f'''
        INSERT INTO {SCHEMA}.subscription_payments
            (company_id, user_id, tariff_id, period, days, amount, status, period_end, method, provider_slug,
             provider_payment_id, paid_at)
        VALUES (%s, %s, %s, %s, %s, 0, 'paid', %s, 'coupon', 'coupon', %s, NOW()) RETURNING id
    ''', (company_id, user_id, coupon['tariff_id'], coupon['period'], coupon['days'], period_end, coupon['code']))
    payment_id = cur.fetchone()[0]
    cur.execute(f'''
        INSERT INTO {SCHEMA}.subscription_coupon_activations (coupon_id, company_id, user_id, payment_id, period_end)
        VALUES (%s, %s, %s, %s, %s)
    ''', (coupon['id'], company_id, user_id, payment_id, period_end))
    return {**coupon, 'period_end': period_end.isoformat()}, None

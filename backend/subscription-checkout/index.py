import json
import os
from typing import Any, Dict

import psycopg2
from auth_guard import guard, is_platform_admin
import billing
import coupons
import downgrade
import tbank_billing

SCHEMA = 't_p83864310_fintech_payment_reco'
PAY_ROLES = ('owner', 'admin')


def respond(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(payload, ensure_ascii=False, default=str),
        'isBase64Encoded': False
    }


def member_role(cur, company_id, user_id):
    cur.execute(f'''
        SELECT r.slug FROM {SCHEMA}.company_users cu JOIN {SCHEMA}.roles r ON r.id = cu.role_id
        WHERE cu.company_id = %s AND cu.user_id = %s AND cu.status = 'active'
    ''', (company_id, user_id))
    row = cur.fetchone()
    return row[0] if row else None


def _origin(event: Dict[str, Any]) -> str:
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    return headers.get('origin') or ''


def autopay_view(cur, company_id) -> Dict[str, Any]:
    cur.execute(f'''
        SELECT s.auto_renew, s.renew_period, c.pan, c.exp_date, c.provider_slug
        FROM {SCHEMA}.subscriptions s
        LEFT JOIN {SCHEMA}.subscription_cards c ON c.id = s.card_id AND c.is_active = true
        WHERE s.company_id = %s
    ''', (company_id,))
    r = cur.fetchone()
    if not r:
        return {'auto_renew': False, 'period': 'month', 'card': None}
    return {'auto_renew': bool(r[0]) and bool(r[2]), 'period': r[1] or 'month',
            'card': {'pan': r[2], 'exp_date': r[3], 'provider': r[4] or 'tbank'} if r[2] else None}


def admin_test(event: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    '''
    Тест оплаты Т‑Банка из админки (только админ платформы, работает и при выключенном приёме оплаты):
    test_checkout {company_id, tariff_slug, period} - ссылка на форму с сохранением карты (Recurrent=Y)
    test_charge {company_id} - списание по сохранённой карте компании прямо сейчас (как автопродление)
    test_status {payment_id} - статус платежа (с запросом GetState)
    test_checkout {..., scenario: "sale"} - обычная продажа без сохранения карты
    test_cancel {payment_id, amount?} - отмена неоплаченного или возврат оплаченного (amount - частичный возврат)
    '''
    user_id = event.get('session_user_id')
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        if not user_id or not is_platform_admin(cur, user_id):
            return respond(403, {'error': 'Только для администратора платформы'})
        action = body['action']
        test_company = body.get('company_id')
        if not test_company and body.get('payment_id'):
            cur.execute(f'SELECT company_id FROM {SCHEMA}.subscription_payments WHERE id = %s', (body.get('payment_id'),))
            found = cur.fetchone()
            test_company = found[0] if found else None
        terminal = tbank_billing.load_terminal(cur, only_enabled=False, company_id=test_company)
        if not terminal:
            return respond(400, {'error': 'Терминал Т‑Банка не подключён'})
        if action == 'test_cancel':
            amount = float(body['amount']) if body.get('amount') else None
            result = billing.cancel_payment(cur, terminal, int(body.get('payment_id') or 0), user_id, amount)
            conn.commit()
            payment = None
            if result.get('success'):
                cur.execute(f'SELECT company_id FROM {SCHEMA}.subscription_payments WHERE id = %s', (body.get('payment_id'),))
                payment = billing.refresh(cur, cur.fetchone()[0], int(body['payment_id']))
            return respond(200, {**result, 'payment': payment})
        if action == 'test_last':
            cur.execute(f'''SELECT id, company_id FROM {SCHEMA}.subscription_payments
                            WHERE is_test = true AND provider_slug = 'tbank' ORDER BY id DESC LIMIT 1''')
            row = cur.fetchone()
            if not row:
                return respond(200, {'success': True, 'payment': None})
            result = billing.refresh(cur, row[1], row[0])
            conn.commit()
            return respond(200, {'success': True, 'payment': result})
        if action == 'test_status':
            cur.execute(f'SELECT company_id FROM {SCHEMA}.subscription_payments WHERE id = %s', (body.get('payment_id'),))
            row = cur.fetchone()
            if not row:
                return respond(404, {'error': 'Платёж не найден'})
            result = billing.refresh(cur, row[0], int(body['payment_id']))
            conn.commit()
            return respond(200, {'success': True, 'payment': result})
        company_id = int(body.get('company_id') or 0)
        cur.execute(f'SELECT id FROM {SCHEMA}.companies WHERE id = %s', (company_id,))
        if not cur.fetchone():
            return respond(400, {'error': 'Компания не найдена'})
        tariffs = billing.load_tariffs(cur)
        if action == 'test_checkout':
            tariff = next((t for t in tariffs if t['slug'] == body.get('tariff_slug')), None)
            if not tariff:
                return respond(400, {'error': 'Тариф не найден'})
            period = 'year' if body.get('period') == 'year' else 'month'
            sale = body.get('scenario') == 'sale'
            result = billing.start_checkout(cur, terminal, company_id, user_id, tariff, period, None, not sale,
                                            is_test=True, save_card=not sale, origin=_origin(event))
            conn.commit()
            return respond(200, result)
        cur.execute(f'''
            SELECT s.tariff_id, s.renew_period, c.rebill_id FROM {SCHEMA}.subscriptions s
            JOIN {SCHEMA}.subscription_cards c ON c.id = s.card_id AND c.is_active = true
            WHERE s.company_id = %s
        ''', (company_id,))
        row = cur.fetchone()
        if not row:
            return respond(400, {'error': 'У компании нет сохранённой карты — сначала проведите тестовую оплату'})
        tariff = next((t for t in tariffs if t['id'] == row[0]), None)
        if not tariff:
            return respond(400, {'error': 'Тариф компании недоступен для оплаты'})
        result = billing.charge_saved_card(cur, conn, terminal, company_id, tariff, row[1] or 'month', row[2], user_id,
                                           is_test=True)
        return respond(200, {'success': result['status'] == 'paid', **result})
    finally:
        cur.close()
        conn.close()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Подписка компании: тарифы, история оплат, оплата через Т‑Банк с сохранением карты и автопродление.
    GET ?company_id= - тарифы, текущая подписка, история, карта/автопродление, способ оплаты
    POST {action: "pay", company_id, tariff_slug, period, keep, auto_renew} - при подключённом Т‑Банке
         возвращает payment_url платёжной формы (Recurrent=Y), тариф включается по уведомлению банка;
         без включённой платёжной системы - отказ 409 payments_off (бесплатной активации нет)
    POST {action: "payment_status", company_id, payment_id} - статус после возврата с формы
    POST {action: "autopay", company_id, enabled} - вкл/выкл автопродление
    POST {action: "remove_card", company_id} - забыть карту (автопродление выключается)
    POST {action: "coupon_check"|"coupon_apply", company_id, code} - проверить / применить промокод
    POST {action: "preview", company_id, tariff_slug} - что не помещается в лимиты тарифа
    POST ?tbank_notify=1 - уведомление Т‑Банка (подпись Token), ответ "OK"
    POST {action: "renew_due"} - внутренний вызов планировщика: автосписания по сохранённым картам
    '''
    params = event.get('queryStringParameters') or {}
    if params.get('tbank_notify') == '1' and event.get('httpMethod') == 'POST':
        data = json.loads(event.get('body') or '{}')
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        try:
            ok = billing.handle_notification(cur, data)
            conn.commit()
        finally:
            cur.close()
            conn.close()
        return {'statusCode': 200 if ok else 403, 'headers': {'Content-Type': 'text/plain'},
                'body': 'OK' if ok else 'BAD TOKEN', 'isBase64Encoded': False}

    status_code = (event.get('queryStringParameters') or {}).get('coupon_status')
    if event.get('httpMethod') == 'GET' and status_code:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        try:
            coupon, error = coupons.find(cur, status_code, 0)
        finally:
            cur.close()
            conn.close()
        return {'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'valid': error is None, 'error': error,
                                    'tariff_name': coupon['tariff_name'] if coupon else None,
                                    'period': coupon['period'] if coupon else None}, ensure_ascii=False),
                'isBase64Encoded': False}

    raw_body = json.loads(event.get('body') or '{}') if event.get('httpMethod') == 'POST' else {}
    if raw_body.get('action') in ('test_checkout', 'test_charge', 'test_status', 'test_cancel', 'test_last'):
        denied = guard(event, check_company=False)
        if denied:
            return denied
        return admin_test(event, raw_body)

    denied = guard(event)
    if denied:
        return denied

    method = event.get('httpMethod', 'GET')
    user_id = event.get('session_user_id')
    params = event.get('queryStringParameters') or {}
    body = json.loads(event.get('body') or '{}') if method == 'POST' else {}
    action = body.get('action')

    if action == 'renew_due':
        if user_id:
            return respond(403, {'error': 'Только для планировщика'})
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor()
        try:
            result = billing.renew_due(cur, conn)
            renewed = result.get('renewed') or []
            failed = [r for r in renewed if r['status'] in ('failed', 'canceled')]
            error = 'pending' if result.get('more') else (
                'Т‑Банк не подключён' if result.get('skipped') else
                (f'не списалось: {len(failed)} из {len(renewed)}' if failed else None))
            cur.execute(f'''
                INSERT INTO {billing.SCHEMA}.cron_source_runs (source, company_id, tick, item_key, loaded, error, finished_at)
                VALUES ('subscriptions', 0, %s, '', %s, %s, NOW())
                ON CONFLICT (source, company_id, item_key) DO UPDATE SET
                    tick = EXCLUDED.tick, loaded = EXCLUDED.loaded, error = EXCLUDED.error, finished_at = NOW()
            ''', (str(body.get('cron_tick') or '')[:40], len(renewed) - len(failed), error))
            conn.commit()
            return respond(200, {'success': True, **result})
        finally:
            cur.close()
            conn.close()

    company_id = body.get('company_id') or params.get('company_id')
    if not company_id:
        return respond(400, {'error': 'Не указана компания'})

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        role = member_role(cur, company_id, user_id)
        can_pay = role in PAY_ROLES
        can_coupon = can_pay or bool(user_id and is_platform_admin(cur, user_id))
        terminal = tbank_billing.load_terminal(cur, company_id=company_id)

        if method == 'GET':
            cur.execute(f'''
                SELECT p.id, t.name, p.period, p.days, p.amount, p.status, p.period_end, p.created_at, p.method,
                       p.is_recurring, p.error_message, p.paid_at, p.refund_amount, p.refunded_at,
                       CASE WHEN p.status = 'pending' THEN p.payment_url END,
                       CASE WHEN p.method = 'coupon' THEN p.provider_payment_id END
                FROM {SCHEMA}.subscription_payments p JOIN {SCHEMA}.tariffs t ON t.id = p.tariff_id
                WHERE p.company_id = %s AND (p.status <> 'pending' OR p.created_at > NOW() - INTERVAL '1 day')
                ORDER BY p.created_at DESC LIMIT 100
            ''', (company_id,))
            payments = [{
                'id': r[0], 'tariff_name': r[1], 'period': r[2], 'days': r[3], 'amount': float(r[4]),
                'status': r[5], 'period_end': r[6], 'created_at': r[7], 'method': r[8],
                'is_recurring': r[9], 'error': r[10], 'paid_at': r[11],
                'refund_amount': float(r[12]) if r[12] is not None else None, 'refunded_at': r[13],
                'payment_url': r[14], 'coupon_code': r[15]
            } for r in cur.fetchall()]
            cur.execute(f'''
                SELECT t.modules, t.max_companies, t.max_users, t.max_integrations, t.max_automations
                FROM {SCHEMA}.subscriptions s JOIN {SCHEMA}.tariffs t ON t.id = s.tariff_id
                WHERE s.company_id = %s
            ''', (company_id,))
            r = cur.fetchone()
            current = {
                'modules': r[0] or [], 'max_companies': r[1], 'max_users': r[2],
                'max_integrations': r[3], 'max_automations': r[4]
            } if r else None
            return respond(200, {'success': True, 'tariffs': billing.load_tariffs(cur), 'current': current,
                                 'payments': payments, 'can_pay': can_pay, 'can_coupon': can_coupon,
                                 'provider': 'tbank' if terminal else None,
                                 'autopay': autopay_view(cur, company_id)})

        if action in ('coupon_check', 'coupon_apply'):
            if not can_coupon:
                return respond(403, {'error': 'Применить промокод может только владелец или админ компании'})
            if action == 'coupon_check':
                coupon, error = coupons.find(cur, body.get('code'), company_id)
            else:
                coupon, error = coupons.apply(cur, body.get('code'), company_id, user_id)
                conn.commit() if not error else conn.rollback()
            if error:
                return respond(400, {'error': error})
            return respond(200, {'success': True, 'coupon': coupon})

        if action == 'preview':
            tariff = next((t for t in billing.load_tariffs(cur) if t['slug'] == body.get('tariff_slug')), None)
            if not tariff:
                return respond(400, {'error': 'Тариф не найден'})
            return respond(200, {'success': True, 'overage': downgrade.overage(cur, company_id, tariff, user_id)})

        if action == 'payment_status':
            result = billing.refresh(cur, company_id, int(body.get('payment_id') or 0))
            conn.commit()
            if not result:
                return respond(404, {'error': 'Платёж не найден'})
            return respond(200, {'success': True, 'payment': result})

        if action in ('autopay', 'remove_card'):
            if not (can_coupon if action == 'remove_card' else can_pay):
                return respond(403, {'error': 'Управлять оплатой может только владелец или админ компании'})
            if action == 'remove_card':
                cur.execute(f'''SELECT card_id, customer_key FROM {SCHEMA}.subscription_cards
                                WHERE company_id = %s AND is_active = true AND provider_slug = 'tbank' ''', (company_id,))
                card = cur.fetchone()
                bank_terminal = tbank_billing.load_terminal(cur, only_enabled=False, company_id=company_id)
                if card and card[0] and card[1] and bank_terminal:
                    tbank_billing.call(bank_terminal, 'RemoveCard', {'CardId': card[0], 'CustomerKey': card[1]})
                cur.execute(f'''UPDATE {SCHEMA}.subscription_cards SET is_active = false, updated_at = NOW()
                                WHERE company_id = %s AND is_active = true''', (company_id,))
                cur.execute(f'''UPDATE {SCHEMA}.subscriptions SET auto_renew = false, card_id = NULL,
                                updated_at = NOW() WHERE company_id = %s''', (company_id,))
            else:
                enabled = bool(body.get('enabled'))
                if enabled and not autopay_view(cur, company_id)['card']:
                    return respond(400, {'error': 'Сначала оплатите подписку картой — она сохранится для автопродления'})
                cur.execute(f'UPDATE {SCHEMA}.subscriptions SET auto_renew = %s, updated_at = NOW() WHERE company_id = %s',
                            (enabled, company_id))
            conn.commit()
            return respond(200, {'success': True, 'autopay': autopay_view(cur, company_id)})

        if action == 'pay':
            print(f"pay request company={company_id} user={user_id} role={role} body={body}")
            if not can_pay:
                return respond(403, {'error': 'Оплачивать подписку может только владелец или админ компании'})
            period = body.get('period') or 'month'
            if period not in ('month', 'year'):
                return respond(400, {'error': 'Срок оплаты: месяц или год'})
            tariff = next((t for t in billing.load_tariffs(cur) if t['slug'] == body.get('tariff_slug')), None)
            if not tariff:
                return respond(400, {'error': 'Тариф не найден'})

            over = downgrade.overage(cur, company_id, tariff, user_id)
            keep = body.get('keep') or {}
            if over:
                if 'companies' in over and role != 'owner':
                    return respond(403, {'error': 'Удалить лишние компании может только владелец'})
                problem = downgrade.check_keep(over, keep)
                if problem:
                    return respond(400, {'error': problem, 'overage': over})

            if terminal:
                if body.get('recurring_consent') is not True:
                    return respond(400, {'error': 'Подтвердите согласие на регулярные списания с карты'})
                if body.get('offer_accepted') is not True:
                    return respond(400, {'error': 'Примите условия оферты'})
                result = billing.start_checkout(cur, terminal, int(company_id), user_id, tariff, period,
                                                keep if over else None, body.get('auto_renew', True) is not False,
                                                origin=_origin(event))
                if result.get('payment_id'):
                    cur.execute(f'''UPDATE {SCHEMA}.subscription_payments SET recurring_consent_at = NOW(),
                                    offer_accepted_at = NOW() WHERE id = %s''', (result['payment_id'],))
                conn.commit()
                return respond(200, result)

            # Без подключённой и включённой платёжной системы тариф не активируется: раньше здесь
            # тариф включался бесплатно (method='manual'). Начислить вручную можно из админки.
            print(f"pay blocked company={company_id}: payment system is off")
            return respond(409, {'error': 'Онлайн-оплата временно недоступна. Напишите нам — поможем продлить подписку.',
                                 'code': 'payments_off'})

        return respond(405, {'error': 'Method not allowed'})
    finally:
        cur.close()
        conn.close()
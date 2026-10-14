import json
import os
from typing import Any, Dict

import psycopg2
from auth_guard import guard
import billing
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


def autopay_view(cur, company_id) -> Dict[str, Any]:
    cur.execute(f'''
        SELECT s.auto_renew, s.renew_period, c.pan, c.exp_date
        FROM {SCHEMA}.subscriptions s
        LEFT JOIN {SCHEMA}.subscription_cards c ON c.id = s.card_id AND c.is_active = true
        WHERE s.company_id = %s
    ''', (company_id,))
    r = cur.fetchone()
    if not r:
        return {'auto_renew': False, 'period': 'month', 'card': None}
    return {'auto_renew': bool(r[0]) and bool(r[2]), 'period': r[1] or 'month',
            'card': {'pan': r[2], 'exp_date': r[3]} if r[2] else None}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Подписка компании: тарифы, история оплат, оплата через Т‑Банк с сохранением карты и автопродление.
    GET ?company_id= - тарифы, текущая подписка, история, карта/автопродление, способ оплаты
    POST {action: "pay", company_id, tariff_slug, period, keep, auto_renew} - при подключённом Т‑Банке
         возвращает payment_url платёжной формы (Recurrent=Y), тариф включается по уведомлению банка;
         без платёжной системы - активирует тариф сразу (как раньше)
    POST {action: "payment_status", company_id, payment_id} - статус после возврата с формы
    POST {action: "autopay", company_id, enabled} - вкл/выкл автопродление
    POST {action: "remove_card", company_id} - забыть карту (автопродление выключается)
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
            return respond(200, {'success': True, **billing.renew_due(cur, conn)})
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
        terminal = tbank_billing.load_terminal(cur)

        if method == 'GET':
            cur.execute(f'''
                SELECT p.id, t.name, p.period, p.days, p.amount, p.status, p.period_end, p.created_at, p.method,
                       p.is_recurring, p.error_message
                FROM {SCHEMA}.subscription_payments p JOIN {SCHEMA}.tariffs t ON t.id = p.tariff_id
                WHERE p.company_id = %s AND (p.status <> 'pending' OR p.created_at > NOW() - INTERVAL '1 day')
                ORDER BY p.created_at DESC LIMIT 20
            ''', (company_id,))
            payments = [{
                'id': r[0], 'tariff_name': r[1], 'period': r[2], 'days': r[3], 'amount': float(r[4]),
                'status': r[5], 'period_end': r[6], 'created_at': r[7], 'method': r[8],
                'is_recurring': r[9], 'error': r[10]
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
                                 'payments': payments, 'can_pay': can_pay,
                                 'provider': 'tbank' if terminal else None,
                                 'autopay': autopay_view(cur, company_id)})

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
            if not can_pay:
                return respond(403, {'error': 'Управлять оплатой может только владелец или админ компании'})
            if action == 'remove_card':
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
                result = billing.start_checkout(cur, terminal, int(company_id), user_id, tariff, period,
                                                keep if over else None, body.get('auto_renew', True) is not False)
                conn.commit()
                return respond(200, result)

            removed = {}
            if over:
                removed = downgrade.apply(cur, company_id, downgrade.to_delete(over, keep))
            days, amount = billing.period_terms(tariff, period)
            period_end = billing.activate(cur, company_id, tariff['id'], days)
            cur.execute(f'''
                INSERT INTO {SCHEMA}.subscription_payments
                    (company_id, user_id, tariff_id, period, days, amount, status, period_end, method, paid_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'paid', %s, 'manual', NOW())
            ''', (company_id, user_id, tariff['id'], period, days, amount, period_end))
            conn.commit()
            return respond(200, {'success': True, 'tariff_name': tariff['name'],
                                 'period_end': period_end, 'amount': amount, 'removed': removed})

        return respond(405, {'error': 'Method not allowed'})
    finally:
        cur.close()
        conn.close()

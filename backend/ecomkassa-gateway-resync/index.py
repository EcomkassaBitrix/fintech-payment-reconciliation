import json
import os
import psycopg2
from typing import Dict, Any

from ecomkassa_report import fetch_report, save_receipt_from_report, RECEIPT_DONE_STATUS
from ecomkassa_token import ensure_valid_token
import crm_link
from cron_report import record_cron_run
from auth_guard import guard, subscription_guard

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}

# Не тянем слишком много платежей за один вызов - функция дёргается автоматически
# при каждом открытии "Событий"/"Сверки", а таймаут облачной функции ограничен.
MAX_PAYMENTS_PER_RUN = 20


def _handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Дозагрузка чеков для платежей шлюза Екомкассы (ecomkassa_gateway), которые
    на момент вебхука ещё не были фискализированы (чек не успел пробиться).
    В платформе нет cron/планировщика, поэтому вызывается автоматически с фронта
    при каждом открытии страниц "События" и "Сверка" - проходит по платежам без
    receipt_id, проверяет статус пробития методом report() и довязывает чек,
    как только он готов (status == "done").
    Args: company_id (обязателен)
    Returns: checked (сколько платежей проверено), resolved (сколько довязано)
    '''

    method = event.get('httpMethod', 'POST')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    if method != 'POST':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    body = json.loads(event.get('body') or '{}')
    company_id = body.get('company_id')

    if not company_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'company_id required'}),
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT ui.id, ui.config
            FROM t_p83864310_fintech_payment_reco.user_integrations ui
            JOIN t_p83864310_fintech_payment_reco.integration_providers p ON p.id = ui.provider_id
            WHERE ui.company_id = %s AND p.slug = 'ecomkassa' AND ui.status = 'active'
            ORDER BY ui.id
            LIMIT 1
        ''', (company_id,))

        cash_row = cur.fetchone()
        if not cash_row:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': True, 'checked': 0, 'resolved': 0, 'note': 'Касса Екомкасса не подключена'}),
                'isBase64Encoded': False
            }

        cash_integration_id, cash_config = cash_row
        cash_config = json.loads(cash_config) if isinstance(cash_config, str) else (cash_config or {})
        # Токен Екомкассы живёт 24 часа - если истёк, получаем новый по
        # сохранённым логину/паролю и сразу обновляем config в БД.
        token = ensure_valid_token(cur, cash_integration_id, cash_config)
        store_id = cash_config.get('store_id')
        protocol_version = cash_config.get('protocol_version', 'v4')

        if not token or not store_id:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': True, 'checked': 0, 'resolved': 0, 'note': 'Касса Екомкасса не настроена'}),
                'isBase64Encoded': False
            }

        # Сделки CRM -> чеки кассы (почта + сумма + время). Сбой связывания не мешает дозагрузке чеков.
        deals_linked = 0
        try:
            deals_linked = crm_link.run(cur, token, protocol_version, company_id)
            conn.commit()
            # Сделки, по которым хук Битрикса не дошёл, - находим по ссылке на оплату.
            deals_linked += crm_link.recover_missed_deals(cur, company_id)
            conn.commit()
            # Сделки из воронок без хука и без ссылки - кандидаты по сумме и времени, без связи.
            crm_link.recover_candidate_deals(cur, company_id)
        except Exception as e:
            conn.rollback()
            print(f'crm link failed: {e}')

        # Платежи шлюза без довязанного чека - только успешные статусы имеют смысл
        # (CREATED ещё не оплачен, CANCELED/REJECTED чека никогда не получат).
        cur.execute('''
            SELECT wp.id, wp.payment_id
            FROM t_p83864310_fintech_payment_reco.webhook_payments wp
            JOIN t_p83864310_fintech_payment_reco.user_integrations ui ON ui.id = wp.integration_id
            JOIN t_p83864310_fintech_payment_reco.integration_providers p ON p.id = ui.provider_id
            WHERE wp.company_id = %s AND p.slug = 'ecomkassa_gateway'
              AND wp.receipt_id IS NULL
              AND wp.status IN ('AUTHORIZED', 'CONFIRMED')
            ORDER BY wp.created_at DESC
            LIMIT %s
        ''', (company_id, MAX_PAYMENTS_PER_RUN))

        pending_payments = cur.fetchall()

        checked = 0
        resolved = 0

        for webhook_payment_id, uid in pending_payments:
            checked += 1
            report_data = fetch_report(token, store_id, uid, protocol_version)
            if not report_data or report_data.get('status') != RECEIPT_DONE_STATUS:
                continue

            receipt_id, total_sum, payment_provider = save_receipt_from_report(cur, cash_integration_id, company_id, uid, report_data,
                                                                                 'cron' if body.get('cron_tick') else 'sync')
            if not receipt_id:
                continue

            cur.execute('''
                UPDATE t_p83864310_fintech_payment_reco.webhook_payments
                SET receipt_id = %s,
                    amount = CASE WHEN amount = 0 THEN %s ELSE amount END,
                    payment_provider = COALESCE(%s, payment_provider),
                    updated_at = NOW()
                WHERE id = %s
            ''', (receipt_id, total_sum, payment_provider, webhook_payment_id))
            resolved += 1

        cur.execute('''
            UPDATE t_p83864310_fintech_payment_reco.user_integrations SET last_synced_at = NOW() WHERE id = %s
        ''', (cash_row[0],))
        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'success': True, 'checked': checked, 'resolved': resolved, 'deals_linked': deals_linked}),
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
        record_cron_run(event, resp, 'ecomkassa_receipts', 'resolved')
    return resp

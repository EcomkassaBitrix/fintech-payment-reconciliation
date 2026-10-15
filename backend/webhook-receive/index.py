import json
import os
import psycopg2
import urllib.request
import urllib.error
import time
from typing import Dict, Any

from form_parser import parse_webhook_body
from inbox import save_event, mark_processed
import tbank_handler
import alfabank_handler
import yookassa_api
import cloudpayments_api
import tochka_acquiring_handler
import bitrix24_handler
import crm_link
from ecomkassa_token import ensure_valid_token as ensure_kassa_token
import amocrm_handler
import ecomkassa_gateway_handler
import moyklass_handler
import realtycalendar_handler
import automation
from auth_guard import guard

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}

# Каждый провайдер имеет свой изолированный обработчик и свой event_type -
# события разных провайдеров никогда не смешиваются, даже если прилетят
# в одну и ту же секунду.
EVENT_TYPE_BY_PROVIDER = {
    'tbank': 'payment_status_changed',
    'alfabank': 'payment_status_changed',
    'yookassa': 'payment_status_changed',
    'cloudpayments': 'payment_status_changed',
    'tochka_acquiring': 'payment_status_changed',
    'bitrix24': 'deal_updated',
    'amocrm': 'lead_updated',
    'ecomkassa_gateway': 'payment_status_changed',
    'ecomkassa': 'receipt_status_changed'
}


def link_deal_now(cur, company_id: int, integration_id: int, external_deal_id: str) -> None:
    cur.execute('''
        SELECT id FROM t_p83864310_fintech_payment_reco.crm_deals
        WHERE integration_id = %s AND external_deal_id = %s AND linked_receipt_id IS NULL AND removed_at IS NULL
    ''', (integration_id, str(external_deal_id)))
    row = cur.fetchone()
    if not row:
        return
    cur.execute('''
        SELECT ui.id, ui.config FROM t_p83864310_fintech_payment_reco.user_integrations ui
        JOIN t_p83864310_fintech_payment_reco.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug = 'ecomkassa' AND ui.status = 'active'
        ORDER BY ui.id LIMIT 1
    ''', (company_id,))
    kassa = cur.fetchone()
    token, protocol = None, 'v4'
    if kassa:
        kassa_config = kassa[1] if isinstance(kassa[1], dict) else json.loads(kassa[1] or '{}')
        token = ensure_kassa_token(cur, kassa[0], kassa_config)
        protocol = kassa_config.get('protocol_version', 'v4')
    crm_link.run_for_deal(cur, token, protocol, company_id, row[0])


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Роутер входящих вебхуков от всех провайдеров (эквайринг, CRM).
    Определяет провайдера по уникальному webhook_token, сохраняет сырое событие
    в inbox-таблицу webhook_events (чтобы событие не потерялось и не перепуталось
    с событием другого провайдера), затем передаёт его в изолированный обработчик
    конкретного провайдера.
    '''
    denied = guard(event, public=True)
    if denied:
        return denied


    method = event.get('httpMethod', 'POST')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': '',
            'isBase64Encoded': False
        }

    params = event.get('queryStringParameters', {}) or {}
    # Альфа-Банк по умолчанию шлёт уведомление GET-запросом с параметрами в ссылке.
    # CloudPayments по умолчанию тоже шлёт GET (параметры уведомления в ссылке, TransactionId).
    is_get_callback = method == 'GET' and params.get('token') and (params.get('mdOrder') or params.get('TransactionId'))
    if method != 'POST' and not is_get_callback:
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json; charset=utf-8'},
            'body': json.dumps({'error': True, 'message': 'Запрос с заданными параметрами не поддерживается'}, ensure_ascii=False),
            'isBase64Encoded': False
        }

    webhook_token = params.get('token', '')

    # Общий вебхук OAuth-приложения Точки: интеграцию находим по customerCode/merchantId из подписанного JWT.
    if not webhook_token and params.get('source') == 'tochka':
        raw = event.get('body') or ''
        if event.get('isBase64Encoded'):
            import base64
            raw = base64.b64decode(raw).decode('utf-8', errors='replace')
        token_found, reply = tochka_acquiring_handler.resolve_app_webhook(raw)
        if not token_found:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'ok': True, 'note': reply}, ensure_ascii=False),
                'isBase64Encoded': False
            }
        webhook_token = token_found
        params['token'] = token_found

    if not webhook_token:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Token required'}),
            'isBase64Encoded': False
        }

    headers = event.get('headers', {}) or {}
    content_type = headers.get('Content-Type') or headers.get('content-type') or ''

    raw_body = event.get('body', '{}') or ''
    if event.get('isBase64Encoded'):
        import base64
        raw_body = base64.b64decode(raw_body).decode('utf-8', errors='replace')

    try:
        webhook_data = {} if is_get_callback else parse_webhook_body(raw_body, content_type)
    except Exception:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Invalid body'}),
            'isBase64Encoded': False
        }

    # Робот Битрикс24 «Исходящий вебхук» передаёт номер прямо в ссылке: ?token=...&deal_id={{ID}}
    if isinstance(webhook_data, dict):
        for key in ('deal_id', 'lead_id'):
            if params.get(key) and not webhook_data.get(key):
                webhook_data[key] = params[key]

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT 
                ui.id, 
                ui.company_id,
                ui.config,
                ui.webhook_settings,
                p.slug,
                ui.forward_url
            FROM t_p83864310_fintech_payment_reco.user_integrations ui
            JOIN t_p83864310_fintech_payment_reco.integration_providers p ON p.id = ui.provider_id
            WHERE ui.webhook_token = %s AND ui.status = 'active'
        ''', (webhook_token,))

        integration_row = cur.fetchone()
        if not integration_row:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Integration not found'}),
                'isBase64Encoded': False
            }

        integration_id, company_id, config, webhook_settings, provider_slug, forward_url = integration_row

        if provider_slug == 'cloudpayments' and is_get_callback:
            webhook_data = {k: v for k, v in params.items() if k not in ('token', 'type')}

        if provider_slug == 'alfabank':
            # Параметры уведомления могут быть и в ссылке (GET), и в теле (POST) - собираем вместе,
            # без нашего token: он не входит в контрольную сумму банка.
            merged = {k: v for k, v in params.items() if k != 'token'}
            if isinstance(webhook_data, dict):
                merged.update({k: v for k, v in webhook_data.items() if not isinstance(v, (dict, list))})
            webhook_data = merged

        config = json.loads(config) if isinstance(config, str) else (config or {})
        webhook_settings = json.loads(webhook_settings) if isinstance(webhook_settings, str) else (webhook_settings or {})

        # Шаг 1: событие сразу попадает в inbox как есть, до какой-либо обработки -
        # это гарантирует, что даже при сбое обработчика сырые данные не потеряются.
        event_type = EVENT_TYPE_BY_PROVIDER.get(provider_slug, 'unknown')
        if provider_slug == 'moyklass':
            event_type = moyklass_handler.event_type(webhook_data)
        elif provider_slug == 'realtycalendar':
            event_type = realtycalendar_handler.event_type(webhook_data)
        # Источник для ленты «События»: хук или подтянуто кроном вместо потерянного хука.
        source = webhook_data.get('source') if isinstance(webhook_data, dict) else None
        origin = {'cron_recovery': 'recovery', 'cron_candidate': 'candidate'}.get(source, 'webhook')
        # Кандидат по сумме и времени: только загружаем сделку - без автосвязи и без сценариев.
        is_candidate = origin == 'candidate'
        event_id = save_event(cur, integration_id, company_id, provider_slug, event_type, webhook_data, origin)
        conn.commit()

        # Шаг 2: событие передаётся в обработчик именно своего провайдера.
        webhook_payment_id = None
        external_deal_id = None
        handler_error = None
        skip_note = None
        extra_payment_ids = []

        if provider_slug == 'tbank':
            signature_valid, webhook_payment_id, handler_error = tbank_handler.process(
                cur, integration_id, company_id, config, webhook_settings, webhook_data
            )
            if not signature_valid:
                mark_processed(cur, event_id, 'rejected', handler_error)
                conn.commit()
                return {
                    'statusCode': 403,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': handler_error}),
                    'isBase64Encoded': False
                }
        elif provider_slug == 'tochka_acquiring':
            signature_valid, webhook_payment_id, handler_error, decoded = tochka_acquiring_handler.process(
                cur, integration_id, company_id, config, webhook_settings, raw_body, webhook_data
            )
            if decoded:
                # В событии храним расшифрованные данные, а не голую строку JWT.
                cur.execute('''
                    UPDATE t_p83864310_fintech_payment_reco.webhook_events SET raw_payload = %s WHERE id = %s
                ''', (json.dumps({'decoded': decoded, 'jwt': raw_body[:4000]}, ensure_ascii=False), event_id))
            if not signature_valid:
                mark_processed(cur, event_id, 'rejected', handler_error)
                conn.commit()
                return {
                    'statusCode': 403,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': handler_error}, ensure_ascii=False),
                    'isBase64Encoded': False
                }
        elif provider_slug == 'alfabank':
            signature_valid, webhook_payment_id, handler_error = alfabank_handler.process(
                cur, integration_id, company_id, config, webhook_settings, webhook_data
            )
            if not signature_valid:
                mark_processed(cur, event_id, 'rejected', handler_error)
                conn.commit()
                return {
                    'statusCode': 403,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': handler_error}, ensure_ascii=False),
                    'isBase64Encoded': False
                }
        elif provider_slug == 'yookassa':
            signature_valid, webhook_payment_id, handler_error, skip_note = yookassa_api.process(
                cur, integration_id, company_id, config, webhook_settings, webhook_data
            )
            if not signature_valid:
                mark_processed(cur, event_id, 'rejected', handler_error)
                conn.commit()
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'ok': False, 'error': handler_error}, ensure_ascii=False),
                    'isBase64Encoded': False
                }
            if handler_error and yookassa_api.is_retryable(handler_error):
                # ЮKassa недоступна: не 200 - она повторит уведомление (до 24 часов).
                mark_processed(cur, event_id, 'failed', handler_error)
                conn.commit()
                return {
                    'statusCode': 503,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': handler_error}, ensure_ascii=False),
                    'isBase64Encoded': False
                }
        elif provider_slug == 'cloudpayments':
            signature_valid, webhook_payment_id, handler_error, skip_note = cloudpayments_api.process(
                cur, integration_id, company_id, config, webhook_settings, webhook_data,
                '' if is_get_callback else raw_body, headers, params
            )
            if not signature_valid:
                mark_processed(cur, event_id, 'rejected', handler_error)
                conn.commit()
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'code': 0}),
                    'isBase64Encoded': False
                }
            if handler_error and cloudpayments_api.is_retryable(handler_error):
                mark_processed(cur, event_id, 'failed', handler_error)
                conn.commit()
                return {
                    'statusCode': 503,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': handler_error}, ensure_ascii=False),
                    'isBase64Encoded': False
                }
        elif provider_slug == 'bitrix24':
            _, external_deal_id, handler_error = bitrix24_handler.process(cur, integration_id, company_id, config, webhook_data)
            if handler_error and handler_error.startswith('SKIP:'):
                skip_note, handler_error = handler_error[5:], None
        elif provider_slug == 'amocrm':
            _, external_deal_id, handler_error = amocrm_handler.process(cur, integration_id, company_id, config, webhook_data)
        elif provider_slug == 'moyklass':
            webhook_payment_id, handler_error, skip_note = moyklass_handler.process(
                cur, integration_id, company_id, config, webhook_data
            )
        elif provider_slug == 'realtycalendar':
            rk_ids, handler_error, skip_note = realtycalendar_handler.process(
                cur, integration_id, company_id, config, webhook_data
            )
            if rk_ids:
                webhook_payment_id, extra_payment_ids = rk_ids[0], rk_ids[1:]
            booking = (webhook_data.get('data') or {}).get('booking') if isinstance(webhook_data.get('data'), dict) else None
            if isinstance(booking, dict) and booking.get('id'):
                external_deal_id = str(booking['id'])
        elif provider_slug == 'ecomkassa' and str(webhook_data.get('status') or '').lower() not in ('done', 'fail', 'wait'):
            skip_note = 'Касса принимает только уведомления о пробитых чеках'
        elif provider_slug in ('ecomkassa_gateway', 'ecomkassa'):
            # Касса без шлюза: на её адрес приходят уведомления о чеках, созданных сценариями.
            _, webhook_payment_id, handler_error = ecomkassa_gateway_handler.process(
                cur, integration_id, company_id, config, webhook_settings, webhook_data
            )

        if external_deal_id:
            cur.execute('''
                UPDATE t_p83864310_fintech_payment_reco.webhook_events
                SET external_deal_id = %s
                WHERE id = %s
            ''', (external_deal_id, event_id))

        if skip_note and not handler_error:
            mark_processed(cur, event_id, 'skipped', skip_note)
        else:
            mark_processed(cur, event_id, 'failed' if handler_error else 'processed', handler_error)

        # Автоматизация: задание в журнал на каждый запущенный сценарий.
        # Только запись в таблицу - сбор данных делает отдельный обработчик.
        # Платёж и событие фиксируются ДО автоматизации: её сбой откатывает
        # только постановку заданий, приём платежа не ломается.
        conn.commit()
        jobs_created = 0
        has_cart = provider_slug == 'tbank' and isinstance(webhook_data.get('Receipt'), dict)
        if provider_slug in ('bitrix24', 'amocrm') and not handler_error and external_deal_id and is_candidate:
            cur.execute('''
                UPDATE t_p83864310_fintech_payment_reco.crm_deals SET candidate_receipt_id = %s
                WHERE integration_id = %s AND external_deal_id = %s AND linked_receipt_id IS NULL
            ''', (webhook_data.get('receipt_id'), integration_id, str(external_deal_id)))
            conn.commit()
        if provider_slug in ('bitrix24', 'amocrm') and not handler_error and external_deal_id and not is_candidate:
            # Сделка, убранная как лишний кандидат к чеку, получила свой хук из CRM - она нужна.
            cur.execute('''
                UPDATE t_p83864310_fintech_payment_reco.crm_deals SET removed_at = NULL
                WHERE integration_id = %s AND external_deal_id = %s AND removed_at IS NOT NULL
                  AND webhook_count > 1
            ''', (integration_id, str(external_deal_id)))
            conn.commit()
            # Сразу по хуку CRM ищем чек и платёж этой сделки (почта + сумма + ±5 минут от хука),
            # чтобы в реестре сделка встала в одну группу с ними без ожидания крона.
            try:
                link_deal_now(cur, company_id, integration_id, external_deal_id)
                conn.commit()
            except Exception as e:
                conn.rollback()
                print(f'crm link failed: {e}')
        if provider_slug == 'bitrix24' and not handler_error and not is_candidate:
            try:
                crm_entity, crm_id = bitrix24_handler.extract_entity(webhook_data)
                jobs_created = automation.enqueue_crm_jobs(cur, company_id, integration_id, crm_entity, crm_id, event_id)
                conn.commit()
            except Exception as e:
                conn.rollback()
                jobs_created = 0
                print(f'automation crm enqueue failed: {e}')
        if provider_slug == 'amocrm' and not handler_error and external_deal_id and not is_candidate:
            try:
                jobs_created = automation.enqueue_crm_jobs(cur, company_id, integration_id, 'deal', external_deal_id, event_id, 'AmoCRM')
                conn.commit()
            except Exception as e:
                conn.rollback()
                jobs_created = 0
                print(f'automation amocrm enqueue failed: {e}')
        if (webhook_payment_id or has_cart) and not handler_error:
            try:
                jobs_created = automation.enqueue_payment_jobs(cur, company_id, integration_id, webhook_payment_id, event_id)
                for extra_id in extra_payment_ids:
                    jobs_created += automation.enqueue_payment_jobs(cur, company_id, integration_id, extra_id, event_id)
                if has_cart:
                    jobs_created += automation.wake_payment_jobs(cur, integration_id, webhook_data.get('PaymentId'))
                conn.commit()
            except Exception as e:
                conn.rollback()
                jobs_created = 0
                print(f'automation enqueue failed: {e}')

        cur.execute('''
            UPDATE t_p83864310_fintech_payment_reco.user_integrations 
            SET last_webhook_at = NOW(), 
                webhook_count = webhook_count + 1,
                updated_at = NOW()
            WHERE id = %s
        ''', (integration_id,))

        # Любое уведомление компании заодно дожимает задания, у которых подошло
        # время повтора, - не дожидаясь открытия раздела «Автоматизация».
        due_jobs = False
        if not jobs_created:
            try:
                due_jobs = automation.has_due_jobs(cur, company_id)
            except Exception as e:
                print(f'automation due check failed: {e}')

        conn.commit()

        if jobs_created or due_jobs:
            automation.signal_processor(company_id)

        if forward_url and webhook_payment_id:
            start_time = int(time.time() * 1000)
            status_code = None
            error_message = None

            try:
                req = urllib.request.Request(
                    forward_url,
                    data=json.dumps(webhook_data).encode('utf-8'),
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    status_code = response.status
            except urllib.error.HTTPError as e:
                status_code = e.code
                error_message = f"HTTP {e.code}: {e.reason}"
            except urllib.error.URLError as e:
                status_code = 0
                error_message = f"URL Error: {str(e.reason)}"
            except Exception as e:
                status_code = 0
                error_message = f"Error: {str(e)}"

            response_time = int(time.time() * 1000) - start_time

            cur.execute('''
                INSERT INTO t_p83864310_fintech_payment_reco.webhook_forward_logs 
                (webhook_payment_id, forward_url, status_code, error_message, response_time_ms)
                VALUES (%s, %s, %s, %s, %s)
            ''', (webhook_payment_id, forward_url, status_code, error_message, response_time))
            conn.commit()

        if provider_slug == 'cloudpayments':
            # CloudPayments ждёт JSON {"code": 0}, иначе считает уведомление недоставленным.
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'code': 0}),
                'isBase64Encoded': False
            }

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'text/plain'},
            'body': 'OK',
            'isBase64Encoded': False
        }

    except Exception as e:
        conn.rollback()
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)}),
            'isBase64Encoded': False
        }
    finally:
        cur.close()
        conn.close()
import json
from datetime import timedelta
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

SCHEMA = 't_p83864310_fintech_payment_reco'
ECOMKASSA_BASE_URL = 'https://app.ecomkassa.ru'
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
# Служебные адреса мессенджеров (Wappi ставит их контакту при переписке в Telegram/MAX) - не почта покупателя.
SERVICE_DOMAIN_SUFFIXES = ('.wappi', 'wappi.pro')
# Чек пробит / ссылка оплачена - Битрикс шлёт хук по сделке почти сразу: окно ±5 минут от хука.
HOOK_WINDOW_MIN = 5

# Сколько документов/сделок дорабатываем за один вызов - укладываемся в таймаут функции.
RECEIPTS_PER_RUN = 8
DEALS_PER_RUN = 5
# Насколько далеко назад смотрим: сделки и чеки за последние N дней.
LOOKBACK_DAYS = 14


def _get_json(url: str, headers: Dict[str, str], timeout: float = 4.0) -> Optional[Any]:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None


def _emails(value: Any) -> List[str]:
    found = {m.lower() for m in EMAIL_RE.findall(json.dumps(value, ensure_ascii=False))}
    return sorted(e for e in found if not e.endswith(SERVICE_DOMAIN_SUFFIXES))


def fill_receipt_emails(cur, token: str, protocol_version: str, company_id: int,
                        receipt_ids: Optional[List[int]] = None) -> int:
    '''Почта покупателя из чека Екомкассы (блок client в формате АТОЛ) - в ecomkassa_receipts.customer_email.'''
    if receipt_ids is not None:
        if not receipt_ids:
            return 0
        cur.execute(f'''
            SELECT id, order_id FROM {SCHEMA}.ecomkassa_receipts
            WHERE id = ANY(%s) AND NOT customer_checked
        ''', (receipt_ids,))
    else:
        cur.execute(f'''
            SELECT id, order_id FROM {SCHEMA}.ecomkassa_receipts
            WHERE company_id = %s AND NOT customer_checked AND removed_at IS NULL AND status = 'done'
              AND created_at > NOW() - make_interval(days => %s)
            ORDER BY id DESC LIMIT %s
        ''', (company_id, LOOKBACK_DAYS, RECEIPTS_PER_RUN))
    rows = cur.fetchall()
    if not rows:
        return 0
    fmt = 'atol-5' if protocol_version == 'v5' else 'atol-4'
    with ThreadPoolExecutor(max_workers=len(rows)) as pool:
        docs = list(pool.map(
            lambda r: _get_json(f'{ECOMKASSA_BASE_URL}/api/mobile/v1/orders/{r[1]}/{fmt}', {'Token': token}), rows))
    filled = 0
    for (receipt_id, _), doc in zip(rows, docs):
        if not isinstance(doc, dict):
            continue
        client = (doc.get('receipt') or {}).get('client') or {}
        email = (client.get('email') or '').strip().lower() or None
        if email and email.endswith(SERVICE_DOMAIN_SUFFIXES):
            email = None
        cur.execute(f'''
            UPDATE {SCHEMA}.ecomkassa_receipts SET customer_email = %s, customer_checked = true WHERE id = %s
        ''', (email, receipt_id))
        filled += 1 if email else 0
    return filled


def fill_deal_emails(cur, company_id: int, deal_row_id: Optional[int] = None) -> None:
    '''Почты покупателя по сделке: из полей самой сделки и из контакта (crm.contact.get).'''
    cur.execute(f'''
        SELECT d.id, d.raw_data, ui.config
        FROM {SCHEMA}.crm_deals d
        JOIN {SCHEMA}.user_integrations ui ON ui.id = d.integration_id
        WHERE d.company_id = %s AND d.provider_slug = 'bitrix24' AND d.customer_emails IS NULL
          AND d.updated_at > NOW() - make_interval(days => %s)
          AND (%s::int IS NULL OR d.id = %s::int)
        ORDER BY d.updated_at DESC LIMIT %s
    ''', (company_id, LOOKBACK_DAYS, deal_row_id, deal_row_id, DEALS_PER_RUN))
    for deal_id, raw, config in cur.fetchall():
        raw = raw if isinstance(raw, dict) else json.loads(raw or '{}')
        config = config if isinstance(config, dict) else json.loads(config or '{}')
        emails = set(_emails(raw))
        contact_id = str(raw.get('CONTACT_ID') or '')
        webhook_url = (config.get('webhook_url') or '').rstrip('/')
        if contact_id.isdigit() and webhook_url:
            contact = _get_json(f'{webhook_url}/crm.contact.get.json?id={contact_id}', {})
            if isinstance(contact, dict):
                emails.update(_emails((contact.get('result') or {}).get('EMAIL') or []))
        cur.execute(f'UPDATE {SCHEMA}.crm_deals SET customer_emails = %s WHERE id = %s',
                    (','.join(sorted(emails)), deal_id))


WEBHOOK_RECEIVE_URL = 'https://functions.poehali.dev/a923b457-57a6-4eb2-b566-9a9d65cb04e8'
# Поле сделки, куда приложение Екомкассы в Битриксе пишет ссылку на оплату.
BITRIX_PAY_LINK_FIELD = 'UF_CRM_URLFORPAYECOMKASSA'
RECOVER_PER_RUN = 4
RECOVER_LOOKBACK_HOURS = 48


def recover_missed_deals(cur, company_id: int) -> int:
    '''
    Страховка от потерянных хуков Битрикса и AmoCRM: оплаченный счёт Екомкассы есть, а сделки с его
    ссылкой на оплату у нас нет - ищем сделку в CRM по ссылке (в AmoCRM - по полю
    «Ссылка на оплату Ecom», точное совпадение) и прогоняем её через
    обычный приём хука (событие, сделка, связь с чеком, сценарии автоматизации).
    Берётся сделка в успешной стадии; интеграция - та, где уже есть сделки этой воронки.
    '''
    cur.execute(f'''
        SELECT DISTINCT r.raw_data->'invoice_payload'->>'link'
        FROM {SCHEMA}.ecomkassa_receipts r
        WHERE r.company_id = %s AND r.removed_at IS NULL AND r.status = 'done'
          AND (r.raw_data->'invoice_payload'->>'link') LIKE 'http%%'
          AND r.created_at > NOW() - make_interval(hours => %s)
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.crm_deals o WHERE o.linked_receipt_id = r.id)
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.crm_deals o WHERE o.company_id = r.company_id
                          AND o.raw_data->>%s = r.raw_data->'invoice_payload'->>'link')
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.crm_deals o, jsonb_each_text(o.raw_data) f
                          WHERE o.company_id = r.company_id AND o.provider_slug = 'amocrm'
                            AND f.value = r.raw_data->'invoice_payload'->>'link')
        LIMIT %s
    ''', (company_id, RECOVER_LOOKBACK_HOURS, BITRIX_PAY_LINK_FIELD, RECOVER_PER_RUN))
    links = [r[0] for r in cur.fetchall()]
    if not links:
        return 0
    cur.execute(f'''
        SELECT ui.id, ui.config, ui.webhook_token,
               ARRAY(SELECT DISTINCT d.raw_data->>'CATEGORY_ID' FROM {SCHEMA}.crm_deals d WHERE d.integration_id = ui.id),
               ui.last_webhook_at
        FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug = 'bitrix24' AND ui.status = 'active' AND ui.webhook_token IS NOT NULL
        ORDER BY ui.last_webhook_at DESC NULLS LAST, ui.id
    ''', (company_id,))
    portals: Dict[str, List[Any]] = {}
    for ui_id, config, token, categories, _ in cur.fetchall():
        config = config if isinstance(config, dict) else json.loads(config or '{}')
        url = (config.get('webhook_url') or '').rstrip('/')
        if url:
            portals.setdefault(url, []).append((ui_id, token, set(c for c in categories if c)))
    def lookup(link: str):
        for url, integrations in portals.items():
            query = urllib.parse.urlencode([(f'filter[{BITRIX_PAY_LINK_FIELD}]', link), ('select[]', 'ID'),
                                            ('select[]', 'CATEGORY_ID'), ('select[]', 'STAGE_SEMANTIC_ID')])
            found = _get_json(f'{url}/crm.deal.list.json?{query}', {}, timeout=2.5)
            deals = [d for d in ((found or {}).get('result') or []) if d.get('STAGE_SEMANTIC_ID') == 'S']
            if deals:
                category = str(deals[0].get('CATEGORY_ID') or '0')
                target = next((i for i in integrations if category in i[2]), integrations[0])
                return target, str(deals[0]['ID'])
        return None

    amo = _amo_accounts(cur, company_id)
    # Поле «Ссылка на оплату Ecom» в каждом аккаунте AmoCRM и недавние сделки с заполненной ссылкой.
    amo_ctx = []
    for base, token, integrations in amo:
        field_id = _amo_pay_link_field(base, token)
        amo_ctx.append((base, token, integrations, field_id, _amo_recent_by_link(base, token, field_id)))

    def pick(leads: List[Dict[str, Any]], integrations: List[Any]):
        # Точное совпадение ссылки: берём успешную сделку, иначе любую не проигранную.
        leads = [l for l in leads if l.get('status_id') != AMO_LOST_STATUS_ID]
        leads.sort(key=lambda l: (l.get('status_id') != AMO_WON_STATUS_ID, l.get('created_at') or 0))
        if not leads:
            return None
        pipeline = str(leads[0].get('pipeline_id') or '')
        target = next((i for i in integrations if pipeline in i[2]), integrations[0])
        return target, str(leads[0]['id'])

    def lookup_any(link: str):
        hit = lookup(link) if portals else None
        if hit:
            return hit
        for base, token, integrations, field_id, recent in amo_ctx:
            if not field_id:
                continue
            hit = pick(recent.get(link) or [], integrations)
            if hit:
                return hit
            found = _get_json(f'{base}/api/v4/leads?' + urllib.parse.urlencode({'query': link, 'limit': 10}),
                              {'Authorization': f'Bearer {token}'}, timeout=2.5)
            leads = [l for l in (((found or {}).get('_embedded') or {}).get('leads') or [])
                     if _amo_field_value(l, field_id) == link]
            hit = pick(leads, integrations)
            if hit:
                return hit
        return None

    with ThreadPoolExecutor(max_workers=len(links)) as pool:
        hits = [h for h in pool.map(lookup_any, links) if h]
    if hits:
        with ThreadPoolExecutor(max_workers=len(hits)) as pool:
            list(pool.map(lambda h: _send_hook(h[0][1], h[1]), hits))
    for target, deal_id in hits:
        print(f'crm recover: deal {deal_id} by pay link -> integration {target[0]}')
    sent = len(hits)
    return sent


CANDIDATE_WINDOW_MIN = 5
CANDIDATE_MIN_AGE_MIN = 10
CANDIDATES_PER_RECEIPT = 3


def recover_candidate_deals(cur, company_id: int) -> int:
    '''
    Сделки из воронок без хука и без ссылки на оплату: для оплаченного счёта/чека без сделки ищем
    в Битриксе сделки на ту же сумму, сменившие стадию в пределах ±5 минут от оплаты, и загружаем
    их как кандидатов - БЕЗ связи и без сценариев: связывает человек вручную в «Транзакциях».
    Каждый чек ищется один раз (не раньше чем через 10 минут, после поиска по ссылке на оплату).
    '''
    cur.execute(f'''
        SELECT r.id, r.total_sum, r.doc_datetime
        FROM {SCHEMA}.ecomkassa_receipts r
        WHERE r.company_id = %s AND r.removed_at IS NULL AND r.status = 'done' AND r.deal_search_at IS NULL
          AND r.total_sum > 0 AND r.doc_datetime IS NOT NULL
          AND COALESCE(r.order_type, 'VCHR') IN ('INVC', 'VCHR') AND COALESCE(r.is_correction, false) = false
          AND r.created_at > NOW() - make_interval(hours => %s)
          AND r.created_at < NOW() - make_interval(mins => %s)
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.crm_deals o
                          WHERE o.linked_receipt_id = r.id OR o.candidate_receipt_id = r.id)
        ORDER BY r.id DESC LIMIT %s
    ''', (company_id, RECOVER_LOOKBACK_HOURS, CANDIDATE_MIN_AGE_MIN, RECOVER_PER_RUN))
    receipts = cur.fetchall()
    if not receipts:
        return 0
    cur.execute(f'''
        UPDATE {SCHEMA}.ecomkassa_receipts SET deal_search_at = NOW() WHERE id = ANY(%s)
    ''', ([r[0] for r in receipts],))
    portals = _bitrix_portals(cur, company_id)
    amo = _amo_accounts(cur, company_id)
    if not portals and not amo:
        return 0

    def lookup(receipt):
        receipt_id, total, paid_at = receipt
        found_all = []
        for url, integrations in portals.items():
            query = urllib.parse.urlencode([
                ('filter[OPPORTUNITY]', f'{float(total):.2f}'),
                ('filter[>MOVED_TIME]', (paid_at - timedelta(minutes=CANDIDATE_WINDOW_MIN)).strftime('%Y-%m-%dT%H:%M:%S+00:00')),
                ('filter[<MOVED_TIME]', (paid_at + timedelta(minutes=CANDIDATE_WINDOW_MIN)).strftime('%Y-%m-%dT%H:%M:%S+00:00')),
                ('select[]', 'ID'), ('select[]', 'CATEGORY_ID')])
            found = _get_json(f'{url}/crm.deal.list.json?{query}', {}, timeout=2.5)
            for d in ((found or {}).get('result') or [])[:CANDIDATES_PER_RECEIPT]:
                category = str(d.get('CATEGORY_ID') or '0')
                target = next((i for i in integrations if category in i[2]), integrations[0])
                found_all.append((target, str(d['ID']), receipt_id))
        for base, token, integrations in amo:
            paid_ts = int(paid_at.timestamp())
            window = CANDIDATE_WINDOW_MIN * 60
            query = urllib.parse.urlencode([
                ('filter[price][from]', int(float(total))), ('filter[price][to]', int(float(total)) + 1),
                ('filter[updated_at][from]', paid_ts - window), ('filter[updated_at][to]', paid_ts + window),
                ('limit', CANDIDATES_PER_RECEIPT * 3)])
            found = _get_json(f'{base}/api/v4/leads?{query}', {'Authorization': f'Bearer {token}'}, timeout=2.5)
            leads = [l for l in (((found or {}).get('_embedded') or {}).get('leads') or [])
                     if abs(float(l.get('price') or 0) - float(total)) < 0.01][:CANDIDATES_PER_RECEIPT]
            for l in leads:
                pipeline = str(l.get('pipeline_id') or '')
                target = next((i for i in integrations if pipeline in i[2]), integrations[0])
                found_all.append((target, str(l['id']), receipt_id))
        return found_all

    with ThreadPoolExecutor(max_workers=len(receipts)) as pool:
        hits = [h for group in pool.map(lookup, receipts) for h in group]
    if hits:
        with ThreadPoolExecutor(max_workers=len(hits)) as pool:
            list(pool.map(lambda h: _send_hook(h[0][1], h[1], 'cron_candidate', h[2]), hits))
    for target, deal_id, receipt_id in hits:
        print(f'crm candidate: deal {deal_id} for receipt {receipt_id} -> integration {target[0]}')
    return len(hits)


def _bitrix_portals(cur, company_id: int) -> Dict[str, List[Any]]:
    '''Порталы Битрикса компании: ссылка API -> интеграции (id, токен хука, воронки их сделок).'''
    cur.execute(f'''
        SELECT ui.id, ui.config, ui.webhook_token,
               ARRAY(SELECT DISTINCT d.raw_data->>'CATEGORY_ID' FROM {SCHEMA}.crm_deals d WHERE d.integration_id = ui.id)
        FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug = 'bitrix24' AND ui.status = 'active' AND ui.webhook_token IS NOT NULL
        ORDER BY ui.last_webhook_at DESC NULLS LAST, ui.id
    ''', (company_id,))
    portals: Dict[str, List[Any]] = {}
    for ui_id, config, token, categories in cur.fetchall():
        config = config if isinstance(config, dict) else json.loads(config or '{}')
        url = (config.get('webhook_url') or '').rstrip('/')
        if url:
            portals.setdefault(url, []).append((ui_id, token, set(c for c in categories if c)))
    return portals


AMO_WON_STATUS_ID = 142
AMO_LOST_STATUS_ID = 143
# Поле сделки AmoCRM, куда приложение Екомкассы пишет ссылку на оплату.
AMO_PAY_LINK_FIELD_NAME = 'ссылка на оплату ecom'
AMO_RECENT_PAGES = 2


def _amo_pay_link_field(base: str, token: str) -> Optional[int]:
    '''ID поля «Ссылка на оплату Ecom» в сделках аккаунта AmoCRM (по названию, без учёта регистра).'''
    for page in (1, 2):
        res = _get_json(f'{base}/api/v4/leads/custom_fields?limit=250&page={page}',
                        {'Authorization': f'Bearer {token}'}, timeout=2.5)
        fields = ((res or {}).get('_embedded') or {}).get('custom_fields') or []
        for f in fields:
            if ' '.join(str(f.get('name') or '').lower().split()) == AMO_PAY_LINK_FIELD_NAME:
                return f.get('id')
        if len(fields) < 250:
            break
    return None


def _amo_field_value(lead: Dict[str, Any], field_id: Optional[int]) -> Optional[str]:
    for f in lead.get('custom_fields_values') or []:
        if f.get('field_id') == field_id:
            values = [str(v.get('value') or '').strip() for v in f.get('values') or []]
            return next((v for v in values if v), None)
    return None


def _amo_recent_by_link(base: str, token: str, field_id: Optional[int]) -> Dict[str, List[Dict[str, Any]]]:
    '''Сделки, изменённые за последние 48 часов, сгруппированные по ссылке на оплату.'''
    out: Dict[str, List[Dict[str, Any]]] = {}
    if not field_id:
        return out
    since = int(time.time()) - RECOVER_LOOKBACK_HOURS * 3600
    for page in range(1, AMO_RECENT_PAGES + 1):
        query = urllib.parse.urlencode({'filter[updated_at][from]': since, 'limit': 250, 'page': page})
        res = _get_json(f'{base}/api/v4/leads?{query}', {'Authorization': f'Bearer {token}'}, timeout=3.0)
        leads = ((res or {}).get('_embedded') or {}).get('leads') or []
        for l in leads:
            link = _amo_field_value(l, field_id)
            if link:
                out.setdefault(link, []).append(l)
        if len(leads) < 250:
            break
    return out


def _amo_base(subdomain: str) -> str:
    host = re.sub(r'^https?://', '', str(subdomain or '').strip()).split('/')[0]
    return f'https://{host if "." in host else host + ".amocrm.ru"}' if host else ''


def _amo_accounts(cur, company_id: int) -> List[Any]:
    '''Аккаунты AmoCRM компании: (адрес API, токен, интеграции (id, токен хука, воронки их сделок)).'''
    cur.execute(f'''
        SELECT ui.id, ui.config, ui.webhook_token,
               ARRAY(SELECT DISTINCT d.raw_data->>'CATEGORY_ID' FROM {SCHEMA}.crm_deals d WHERE d.integration_id = ui.id)
        FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND p.slug = 'amocrm' AND ui.status = 'active' AND ui.webhook_token IS NOT NULL
        ORDER BY ui.last_webhook_at DESC NULLS LAST, ui.id
    ''', (company_id,))
    accounts: Dict[Any, List[Any]] = {}
    for ui_id, config, token, categories in cur.fetchall():
        config = config if isinstance(config, dict) else json.loads(config or '{}')
        base, api_key = _amo_base(config.get('subdomain', '')), str(config.get('api_key') or '').strip()
        if base and api_key:
            accounts.setdefault((base, api_key), []).append((ui_id, token, set(c for c in categories if c)))
    return [(b, k, i) for (b, k), i in accounts.items()]


def _send_hook(webhook_token: str, deal_id: str, source: str = 'cron_recovery', receipt_id: Optional[int] = None) -> None:
    '''Тот же приём, что у хука Битрикса; ответа не ждём - обработка идёт сама.'''
    body = json.dumps({'deal_id': deal_id, 'source': source, 'receipt_id': receipt_id}).encode('utf-8')
    url = f'{WEBHOOK_RECEIVE_URL}?' + urllib.parse.urlencode({'token': webhook_token, 'deal_id': deal_id})
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=body, method='POST',
                                                      headers={'Content-Type': 'application/json'}), timeout=1).close()
    except Exception:
        pass


def link_deals_by_pay_link(cur, company_id: int, deal_row_id: Optional[int] = None) -> int:
    '''
    Сделка -> оплаченный счёт Екомкассы по ссылке на оплату: приложение Екомкассы в Битриксе
    пишет ссылку (QR СБП) в поле сделки, та же ссылка есть в счёте (invoice_payload.link).
    Точный ключ - работает и когда по сделке есть заказ от сценария, и когда в чеке нет почты.
    '''
    # Хуки копий сделки приходят одновременно - без блокировки каждый видит счёт свободным.
    # pg_advisory_xact_lock запрещён в базе - блокируем строку компании до конца транзакции.
    cur.execute(f'SELECT id FROM {SCHEMA}.companies WHERE id = %s FOR UPDATE', (int(company_id),))
    cur.execute(f'''
        UPDATE {SCHEMA}.crm_deals d SET linked_receipt_id = m.receipt_id, linked_at = NOW()
        FROM (
            -- Роботы Битрикса копируют сделку вместе с полем ссылки на оплату: один счёт - одна
            -- сделка. Берём успешную, затем самую раннюю по дате создания в Битриксе (оригинал).
            SELECT DISTINCT ON (c.receipt_id) c.deal_id, c.receipt_id
            FROM (
            SELECT d2.id AS deal_id, d2.raw_data AS deal_raw, (
                SELECT r.id FROM {SCHEMA}.ecomkassa_receipts r
                WHERE r.company_id = d2.company_id AND r.removed_at IS NULL AND r.status = 'done'
                  AND (r.raw_data->'invoice_payload'->>'link') LIKE 'http%%'
                  AND EXISTS (SELECT 1 FROM jsonb_each_text(d2.raw_data) f
                              WHERE f.value = r.raw_data->'invoice_payload'->>'link')
                  AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.crm_deals o WHERE o.linked_receipt_id = r.id AND o.id <> d2.id)
                ORDER BY r.id DESC LIMIT 1
            ) AS receipt_id
            FROM {SCHEMA}.crm_deals d2
            WHERE d2.company_id = %s AND d2.linked_receipt_id IS NULL AND d2.removed_at IS NULL
              AND d2.updated_at > NOW() - make_interval(days => %s)
              AND (%s::int IS NULL OR d2.id = %s::int)
            ) c
            WHERE c.receipt_id IS NOT NULL
            ORDER BY c.receipt_id, (c.deal_raw->>'STAGE_SEMANTIC_ID' = 'S' OR c.deal_raw->>'STAGE_ID' LIKE '%%WON') DESC,
                     c.deal_raw->>'DATE_CREATE', c.deal_id
        ) m
        WHERE d.id = m.deal_id
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.crm_deals o WHERE o.linked_receipt_id = m.receipt_id)
        RETURNING d.id
    ''', (company_id, LOOKBACK_DAYS, deal_row_id, deal_row_id))
    return len(cur.fetchall())


def link_deals(cur, company_id: int, deal_row_id: Optional[int] = None) -> int:
    '''
    Сделка -> чек/счёт Екомкассы, пока приложение ЕкомКассы не пишет ссылку на оплату в сделку:
    та же почта покупателя, та же сумма, и чек пробит в пределах ±5 минут от одного из хуков
    CRM по этой сделке (хук приходит, когда пробит чек или оплачена ссылка). Из подходящих -
    ближайший ко времени хука; чек, уже связанный с другой сделкой, не берём.
    '''
    cur.execute(f'''
        UPDATE {SCHEMA}.crm_deals d SET linked_receipt_id = m.receipt_id, linked_at = NOW()
        FROM (
            SELECT d2.id AS deal_id, (
                SELECT r.id FROM {SCHEMA}.ecomkassa_receipts r
                JOIN {SCHEMA}.webhook_events we ON we.integration_id = d2.integration_id
                     AND we.external_deal_id = d2.external_deal_id
                     AND r.doc_datetime BETWEEN we.created_at - make_interval(mins => %s)
                                            AND we.created_at + make_interval(mins => %s)
                WHERE r.company_id = d2.company_id AND r.removed_at IS NULL AND r.status = 'done'
                  AND r.customer_email IS NOT NULL
                  AND r.customer_email = ANY(string_to_array(d2.customer_emails, ','))
                  AND r.total_sum = d2.amount
                  AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.crm_deals o WHERE o.linked_receipt_id = r.id AND o.id <> d2.id)
                ORDER BY abs(extract(epoch FROM r.doc_datetime - we.created_at))
                LIMIT 1
            ) AS receipt_id
            FROM {SCHEMA}.crm_deals d2
            WHERE d2.company_id = %s AND d2.linked_receipt_id IS NULL AND d2.removed_at IS NULL
              AND COALESCE(d2.customer_emails, '') <> '' AND d2.amount > 0
              AND d2.updated_at > NOW() - make_interval(days => %s)
              AND (%s::int IS NULL OR d2.id = %s::int)
              -- Заказ по сделке создан сценарием - связь уже есть по UUID заказа, почта не нужна.
              AND NOT EXISTS (
                  SELECT 1 FROM {SCHEMA}.automation_jobs j
                  JOIN {SCHEMA}.automation_scenarios s ON s.id = j.scenario_id
                  JOIN {SCHEMA}.automation_documents ad ON ad.job_id = j.id AND ad.ecom_uuid IS NOT NULL
                  WHERE j.source_type = 'crm_deal' AND j.source_id = d2.external_deal_id
                    AND s.source_integration_id = d2.integration_id)
        ) m
        WHERE d.id = m.deal_id AND m.receipt_id IS NOT NULL
        RETURNING d.id
    ''', (HOOK_WINDOW_MIN, HOOK_WINDOW_MIN, company_id, LOOKBACK_DAYS, deal_row_id, deal_row_id))
    return len(cur.fetchall())


def candidate_receipts(cur, deal_row_id: int) -> List[int]:
    '''Чеки той же суммы, пробитые в окне ±5 минут от хуков сделки, - им нужна почта покупателя.'''
    cur.execute(f'''
        SELECT DISTINCT r.id FROM {SCHEMA}.crm_deals d
        JOIN {SCHEMA}.webhook_events we ON we.integration_id = d.integration_id AND we.external_deal_id = d.external_deal_id
        JOIN {SCHEMA}.ecomkassa_receipts r ON r.company_id = d.company_id AND r.removed_at IS NULL
             AND r.status = 'done' AND NOT r.customer_checked AND r.total_sum = d.amount
             AND r.doc_datetime BETWEEN we.created_at - make_interval(mins => %s) AND we.created_at + make_interval(mins => %s)
        WHERE d.id = %s
    ''', (HOOK_WINDOW_MIN, HOOK_WINDOW_MIN, deal_row_id))
    return [r[0] for r in cur.fetchall()]


def run(cur, token: str, protocol_version: str, company_id: int) -> int:
    '''Один проход связывания сделок CRM с чеками кассы (крон). Returns: сколько сделок связано.'''
    linked = link_deals_by_pay_link(cur, company_id)
    fill_receipt_emails(cur, token, protocol_version, company_id)
    fill_deal_emails(cur, company_id)
    return linked + link_deals(cur, company_id)


def run_for_deal(cur, token: Optional[str], protocol_version: str, company_id: int, deal_row_id: int) -> int:
    '''Связывание сразу по приходу хука CRM: почта сделки, почта чеков-кандидатов, связь.'''
    if link_deals_by_pay_link(cur, company_id, deal_row_id):
        return 1
    fill_deal_emails(cur, company_id, deal_row_id)
    if token:
        fill_receipt_emails(cur, token, protocol_version, company_id, candidate_receipts(cur, deal_row_id))
    return link_deals(cur, company_id, deal_row_id)

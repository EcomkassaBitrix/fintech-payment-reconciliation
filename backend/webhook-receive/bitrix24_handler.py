import json
import urllib.request
import urllib.error
from typing import Any, Dict, Optional, Tuple


STAGE_MAP = {
    'NEW': 'Новая',
    'PREPARATION': 'Подготовка',
    'PREPAYMENT_INVOICE': 'Выставлен счёт',
    'EXECUTING': 'В работе',
    'FINAL_INVOICE': 'Финальный счёт',
    'WON': 'Успешно',
    'LOSE': 'Провалена'
}


def extract_entity(webhook_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    '''
    Объект и ID из вебхука Битрикс24:
    - исходящий вебхук: event=ONCRMDEALUPDATE / ONCRMLEADADD..., data[FIELDS][ID]=123
    - робот/бизнес-процесс: document_id[2]=DEAL_123 или LEAD_123
    - ссылка робота «Исходящий вебхук» с параметрами: ?deal_id=123 / ?lead_id=123
    Returns: ('deal' | 'lead', id)
    '''
    event = str(webhook_data.get('event') or '').upper()
    fields = webhook_data.get('data', {}).get('FIELDS', {}) if isinstance(webhook_data.get('data'), dict) else {}
    item_id = fields.get('ID') if isinstance(fields, dict) else None
    if item_id:
        return ('lead' if 'LEAD' in event else 'deal'), str(item_id)

    document_id = webhook_data.get('document_id')
    if isinstance(document_id, dict):
        raw_ref = document_id.get('2') or document_id.get(2)
        if isinstance(raw_ref, str) and '_' in raw_ref:
            kind, _, ref_id = raw_ref.partition('_')
            if kind.upper() in ('DEAL', 'LEAD') and ref_id.isdigit():
                return kind.lower(), ref_id

    for key, entity in (('deal_id', 'deal'), ('lead_id', 'lead')):
        value = str(webhook_data.get(key) or '').strip()
        if value.isdigit():
            return entity, value
    return None, None


def _extract_deal_id(webhook_data: Dict[str, Any]) -> Optional[str]:
    entity, item_id = extract_entity(webhook_data)
    return item_id if entity == 'deal' else None


def fetch_deal_details(webhook_url: str, deal_id: str) -> Optional[Dict[str, Any]]:
    '''
    Вебхук Битрикс24 присылает только событие и ID сделки (data[FIELDS][ID]),
    полные данные нужно доопросить через crm.deal.get.
    '''
    url = webhook_url.rstrip('/') + f'/crm.deal.get.json?id={deal_id}'
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('result')
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None


def process(cur, integration_id: int, company_id: int, config: Dict[str, Any],
            webhook_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
    '''
    Обрабатывает событие Битрикс24: достаёт ID сделки из вебхука, ходит в crm.deal.get
    за полными данными, сохраняет/обновляет сделку в crm_deals (webhook_count растёт
    при каждом повторном хуке по той же сделке - так лента событий может группировать
    повторы вместо создания дублей).
    Returns: (success, deal_id, error)
    '''
    webhook_url = config.get('webhook_url', '')
    if not webhook_url:
        return False, None, 'webhook_url not configured'

    entity, item_id = extract_entity(webhook_data)
    if entity == 'lead':
        # Лиды в ленту сделок не пишем - их данные соберёт сценарий автоматизации.
        return True, None, None
    deal_id = item_id if entity == 'deal' else None

    if not deal_id:
        return False, None, 'Deal ID not found in webhook payload'

    deal = fetch_deal_details(webhook_url, deal_id)
    if not deal:
        return False, str(deal_id), f'Failed to fetch deal {deal_id} from Bitrix24 API'

    chosen = {str(c) for c in (config.get('deal_categories') or []) if str(c).strip()}
    category = str(deal.get('CATEGORY_ID') or '0')
    if chosen and category not in chosen:
        print(f'bitrix deal {deal_id} skipped: воронка {category} не выбрана в интеграции {integration_id}')
        return True, None, f'SKIP:Сделка #{deal_id} из воронки {category} - она не выбрана в настройках интеграции'

    stage_id = deal.get('STAGE_ID', '')
    stage_name = STAGE_MAP.get(stage_id, stage_id)

    cur.execute('''
        INSERT INTO t_p83864310_fintech_payment_reco.crm_deals (
            integration_id, company_id, provider_slug, external_deal_id,
            title, stage, amount, currency, raw_data, webhook_count, updated_at
        ) VALUES (%s, %s, 'bitrix24', %s, %s, %s, %s, %s, %s, 1, NOW())
        ON CONFLICT (integration_id, external_deal_id) DO UPDATE SET
            title = EXCLUDED.title,
            stage = EXCLUDED.stage,
            amount = EXCLUDED.amount,
            currency = EXCLUDED.currency,
            raw_data = EXCLUDED.raw_data,
            webhook_count = t_p83864310_fintech_payment_reco.crm_deals.webhook_count + 1,
            customer_emails = NULL,
            updated_at = NOW()
    ''', (
        integration_id,
        company_id,
        str(deal_id),
        deal.get('TITLE'),
        stage_name,
        deal.get('OPPORTUNITY'),
        deal.get('CURRENCY_ID'),
        json.dumps(deal)
    ))

    return True, str(deal_id), None
import json
import re
import os
import secrets
import psycopg2
from typing import Dict, Any, Optional
from auth_guard import guard

SCHEMA = 't_p83864310_fintech_payment_reco'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}

# Источник -> категории интеграций, которые можно выбрать как источник
# (None - источник внутренний, без интеграции).
TRIGGERS = {
    'new_payment': ['payments', 'moyklass', 'realtycalendar'],
    'crm_order': ['crm'],
    'discrepancy': None,
}

# Шаблоны действий хранятся в automation_action_templates (правятся в админке платформы).
ACTIONS = {'create_receipt', 'create_order'}

TARGET_CATEGORIES = ['cash_registers']
STATUSES = {'active', 'stopped'}


def respond(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(payload, ensure_ascii=False, default=str),
        'isBase64Encoded': False
    }


def integration_category(cur, company_id: int, integration_id: Optional[int]) -> Optional[str]:
    if not integration_id:
        return None
    cur.execute(f'''
        SELECT c.slug, p.slug FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        JOIN {SCHEMA}.integration_categories c ON c.id = p.category_id
        WHERE ui.id = %s AND ui.company_id = %s
    ''', (integration_id, company_id))
    row = cur.fetchone()
    if not row:
        return None
    # «Мой Класс» - CRM, но платежи учеников приходят как оплаты: источник сценария «Новый платёж».
    return row[1] if row[1] in ('moyklass', 'realtycalendar') else row[0]


def validate(cur, company_id: int, body: Dict[str, Any]) -> Optional[str]:
    name = (body.get('name') or '').strip()
    if not name:
        return 'Укажите название сценария'
    trigger = body.get('trigger_type')
    if trigger not in TRIGGERS:
        return 'Неизвестный источник'
    allowed = TRIGGERS[trigger]
    if allowed:
        if not body.get('source_integration_id'):
            return 'Выберите интеграцию-источник'
        if integration_category(cur, company_id, body.get('source_integration_id')) not in allowed:
            return 'Интеграция не подходит для этого источника'
    action = body.get('action_type')
    if action not in ACTIONS:
        return 'Неизвестное действие'
    if trigger == 'discrepancy' and action != 'create_receipt':
        return 'Для расхождения доступно только действие «Создать чек»'
    cur.execute(f'''
        SELECT action_type, is_active, provider_id, receipt_type, protocol_version, correction_date_source,
               correction_base_number, correction_base_name, agent_settings
        FROM {SCHEMA}.automation_action_templates WHERE code = %s
    ''', (body.get('action_template'),))
    template = cur.fetchone()
    if not template or template[0] != action:
        return 'Неизвестный шаблон действия'
    if not template[1] and not body.get('id'):
        return 'Шаблон действия отключён'
    if not body.get('target_integration_id'):
        return 'Выберите кассу, где выполнить действие'
    if integration_category(cur, company_id, body.get('target_integration_id')) not in TARGET_CATEGORIES:
        return 'Действие можно выполнить только в кассе'
    if template[2]:
        cur.execute(f'SELECT provider_id FROM {SCHEMA}.user_integrations WHERE id = %s', (body.get('target_integration_id'),))
        target = cur.fetchone()
        if not target or target[0] != template[2]:
            return 'Шаблон рассчитан на другую кассу'
    email = str((body.get('correction_settings') or {}).get('default_email') or '').strip() \
        if isinstance(body.get('correction_settings'), dict) else ''
    if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return 'Проверьте почту по умолчанию'
    if template[3] == 'correction':
        cs = body.get('correction_settings') or {}
        if not isinstance(cs, dict):
            return 'Некорректные настройки чека коррекции'
        if template[4] != 'v5':
            if not str(cs.get('correction_base_number') or template[6] or '').strip():
                return 'Укажите номер документа-основания коррекции (обязателен для протокола v4)'
            if not str(template[7] or cs.get('correction_base_name') or '').strip():
                return 'Укажите описание коррекции (обязательно для протокола v4)'
    if template[3] == 'agent':
        agent, error = clean_agent((body.get('correction_settings') or {}).get('agent')
                                   if isinstance(body.get('correction_settings'), dict) else None)
        if error:
            return error
        base = template[8] if isinstance(template[8], dict) else {}
        crm_map = body.get('field_mapping') if trigger == 'crm_order' and isinstance(body.get('field_mapping'), dict) else {}
        if not (base.get('supplier_name') or agent.get('supplier_name') or crm_map.get('agent_supplier_name')):
            return 'Укажите наименование поставщика агентского чека'
        if not (base.get('supplier_inn') or agent.get('supplier_inn') or crm_map.get('agent_supplier_inn')):
                return 'Укажите ИНН поставщика (обязателен для протокола v5)'
    mapping = body.get('field_mapping') or {}
    if not isinstance(mapping, dict):
        return 'Некорректная настройка сопоставления полей'
    if trigger == 'discrepancy':
        try:
            delay = int(mapping.get('delay_minutes') or 60)
        except (TypeError, ValueError):
            return 'Укажите, через сколько минут после оплаты считать, что чека нет'
        if delay < 5 or delay > 10080:
            return 'Задержка расхождения - от 5 минут до 7 суток'
        kind = mapping.get('discrepancy_kind') or 'missing_receipt'
        if kind not in ('missing_receipt', 'pending_invoice'):
            return 'Неизвестный вид расхождения'
        if (mapping.get('verify_mode') or 'none') not in ('none', 'payment_system'):
            return 'Неизвестный тип проверки'
        if kind == 'pending_invoice':
            if mapping.get('verify_mode') != 'payment_system':
                return 'Для счетов «ожидает оплату» нужна проверка в платёжной системе'
            try:
                lookback = int(mapping.get('lookback_days') or 3)
            except (TypeError, ValueError):
                return 'Укажите, за сколько дней смотреть счета'
            if lookback < 1 or lookback > 31:
                return 'Счета можно смотреть за период от 1 до 31 дня'
    if trigger == 'crm_order':
        if mapping.get('entity', 'deal') not in ('deal', 'lead'):
            return 'Выберите объект CRM: сделки или лиды'
        if not mapping.get('order_id'):
            return 'Укажите поле с номером заказа'
        if mapping.get('items_mode', 'products') not in ('products', 'fixed', 'single'):
            return 'Неизвестный способ формирования состава чека'
        if mapping.get('items_mode') == 'fixed' and not mapping.get('fixed_items'):
            return 'Добавьте позиции фиксированного состава чека'
        if mapping.get('items_mode') == 'single' and not (mapping.get('amount') or str(mapping.get('single_item_amount') or '').strip()):
            return 'Для чека одной позицией укажите поле с суммой'
    return None


def _integration(cur, integration_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if not integration_id:
        return None
    cur.execute(f'''
        SELECT id, provider_id, integration_name, config, status FROM {SCHEMA}.user_integrations WHERE id = %s
    ''', (integration_id,))
    r = cur.fetchone()
    if not r:
        return None
    config = json.loads(r[3]) if isinstance(r[3], str) else (r[3] or {})
    return {'id': r[0], 'provider_id': r[1], 'name': r[2], 'config': config, 'status': r[4]}


def _match_integration(cur, company_id: int, src: Dict[str, Any]) -> Optional[int]:
    '''
    Такая же интеграция в другой компании: тот же провайдер, приоритет - тот же
    адрес вебхука CRM, затем то же название, затем любая активная этого провайдера.
    '''
    cur.execute(f'''
        SELECT id, integration_name, config FROM {SCHEMA}.user_integrations
        WHERE company_id = %s AND provider_id = %s AND status = 'active' ORDER BY id
    ''', (company_id, src['provider_id']))
    rows = cur.fetchall()
    url = src['config'].get('webhook_url')
    for r in rows:
        config = json.loads(r[2]) if isinstance(r[2], str) else (r[2] or {})
        if url and config.get('webhook_url') == url:
            return r[0]
    for r in rows:
        if r[1] == src['name']:
            return r[0]
    return rows[0][0] if rows and not url else None


CORRECTION_KEYS = ('correction_base_number', 'correction_base_name', 'default_email', 'cashier_name')
SCENARIO_VATS = {'none', 'vat0', 'vat5', 'vat7', 'vat10', 'vat20', 'vat22',
                 'vat105', 'vat107', 'vat110', 'vat120', 'vat122'}


AGENT_TEXT = {'paying_agent_operation': ('Операция платёжного агента', 24),
              'money_transfer_operator_name': ('Наименование оператора перевода', 64),
              'money_transfer_operator_address': ('Адрес оператора перевода', 243),
              'supplier_name': ('Наименование поставщика', 239)}
AGENT_INN = {'money_transfer_operator_inn': 'ИНН оператора перевода', 'supplier_inn': 'ИНН поставщика'}
AGENT_PHONES = {'paying_agent_phones': 'Телефон платёжного агента',
                'receive_payments_operator_phones': 'Телефон оператора по приёму платежей',
                'money_transfer_operator_phones': 'Телефон оператора перевода',
                'supplier_phones': 'Телефон поставщика'}


def clean_agent(value: Any):
    '''
    Агентские поля сценария - то, что не задано в шаблоне действия.
    Телефоны - список +79991234567. Returns: (dict, error).
    '''
    if not isinstance(value, dict):
        return {}, None
    result: Dict[str, Any] = {}
    for key, (label, limit) in AGENT_TEXT.items():
        text = str(value.get(key) or '').strip()
        if len(text) > limit:
            return {}, f'{label} - не больше {limit} символов'
        if text:
            result[key] = text
    for key, label in AGENT_INN.items():
        inn = re.sub(r'\D', '', str(value.get(key) or ''))
        if inn and len(inn) not in (10, 12):
            return {}, f'{label} - 10 или 12 цифр'
        if inn:
            result[key] = inn
    for key, label in AGENT_PHONES.items():
        raw = value.get(key)
        raw = ','.join(str(x) for x in raw) if isinstance(raw, list) else str(raw or '')
        phones = []
        for part in raw.split(','):
            digits = re.sub(r'[^\d+]', '', part)
            if not digits:
                continue
            if not digits.startswith('+'):
                digits = '+7' + digits[1:] if digits.startswith('8') and len(digits) == 11 else '+' + digits
            if not re.match(r'^\+\d{1,19}$', digits):
                return {}, f'{label}: телефон «{part.strip()}» указан неверно'
            phones.append(digits)
        if phones:
            result[key] = phones
    return result, None


def clean_correction(value: Any) -> Dict[str, Any]:
    '''Поля сценария, не заданные в шаблоне: основание коррекции, почта, кассир, агентские данные.'''
    if not isinstance(value, dict):
        return {}
    result: Dict[str, Any] = {k: str(value[k]).strip()[:256] for k in CORRECTION_KEYS if str(value.get(k) or '').strip()}
    if value.get('vat') in SCENARIO_VATS:
        result['vat'] = value['vat']
    agent, _ = clean_agent(value.get('agent'))
    if agent:
        result['agent'] = agent
    return result


def copy_to_company(cur, conn, company_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    '''
    Копия сценария в другую компанию пользователя. Источник ищется в целевой компании
    (тот же провайдер/вебхук/название), если его нет - копируется со своим адресом хука.
    Касса - только существующая касса того же провайдера в целевой компании.
    Returns: (статус, ответ).
    '''
    target_id = int(body.get('target_company_id') or 0)
    user_id = body.get('user_id')
    if not target_id or not user_id:
        return {'status': 400, 'body': {'error': 'Укажите компанию и пользователя'}}
    cur.execute(f'''
        SELECT COUNT(DISTINCT company_id) FROM {SCHEMA}.company_users
        WHERE user_id = %s AND status = 'active' AND company_id IN (%s, %s)
    ''', (user_id, company_id, target_id))
    if cur.fetchone()[0] < (1 if int(company_id) == target_id else 2):
        return {'status': 403, 'body': {'error': 'Нет доступа к одной из компаний'}}
    cur.execute(f'''
        SELECT name, trigger_type, source_integration_id, action_type, action_template,
               target_integration_id, field_mapping, correction_settings
        FROM {SCHEMA}.automation_scenarios WHERE id = %s AND company_id = %s AND removed_at IS NULL
    ''', (body.get('id'), company_id))
    r = cur.fetchone()
    if not r:
        return {'status': 404, 'body': {'error': 'Сценарий не найден'}}
    name, trigger, src_id, action, template, kassa_id, mapping, correction = r
    mapping = json.loads(mapping) if isinstance(mapping, str) else (mapping or {})

    kassa = _integration(cur, kassa_id)
    new_kassa = _match_integration(cur, target_id, kassa) if kassa else None
    if not new_kassa:
        return {'status': 400, 'body': {'error': f"В выбранной компании нет кассы «{kassa['name'] if kassa else '-'}» того же типа - подключите её и повторите"}}

    new_src, copied_source = None, None
    src = _integration(cur, src_id)
    if src:
        new_src = _match_integration(cur, target_id, src)
        if not new_src:
            cur.execute(f'''
                INSERT INTO {SCHEMA}.user_integrations
                    (legacy_owner_id_unused, provider_id, integration_name, webhook_token, config, status,
                     webhook_settings, forward_url, company_id, sync_interval_hours)
                SELECT legacy_owner_id_unused, provider_id, integration_name, %s, config, 'active',
                       webhook_settings, forward_url, %s, sync_interval_hours
                FROM {SCHEMA}.user_integrations WHERE id = %s
                RETURNING id
            ''', (secrets.token_urlsafe(32), target_id, src['id']))
            new_src = cur.fetchone()[0]
            copied_source = src['name']

    payload = {'name': body.get('name') or name, 'trigger_type': trigger, 'source_integration_id': new_src,
               'action_type': action, 'action_template': template, 'target_integration_id': new_kassa,
               'field_mapping': mapping, 'id': 'copy', 'correction_settings': correction or {}}
    error = validate(cur, target_id, payload)
    if error:
        conn.rollback()
        return {'status': 400, 'body': {'error': error}}
    cur.execute(f'''
        SELECT t.max_automations,
               (SELECT COUNT(*) FROM {SCHEMA}.automation_scenarios a WHERE a.company_id = %s AND a.removed_at IS NULL)
        FROM {SCHEMA}.subscriptions s JOIN {SCHEMA}.tariffs t ON t.id = s.tariff_id
        WHERE s.company_id = %s
    ''', (target_id, target_id))
    limit_row = cur.fetchone()
    if limit_row and limit_row[0] is not None and limit_row[1] >= limit_row[0]:
        conn.rollback()
        return {'status': 403, 'body': {'error': f'В выбранной компании исчерпан лимит автоматизаций по тарифу ({limit_row[0]})'}}
    cur.execute(f'''
        INSERT INTO {SCHEMA}.automation_scenarios
            (company_id, name, trigger_type, source_integration_id, action_type,
             action_template, target_integration_id, field_mapping, status, correction_settings)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'stopped', %s)
        RETURNING id
    ''', (target_id, payload['name'][:200], trigger, new_src, action, template, new_kassa, json.dumps(mapping),
          json.dumps(clean_correction(correction), ensure_ascii=False)))
    new_id = cur.fetchone()[0]
    conn.commit()
    return {'status': 200, 'body': {'success': True, 'id': new_id, 'company_id': target_id,
                                    'copied_source': copied_source}}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Сценарии автоматизации компании: источник (новый платёж, заказ в CRM,
    расхождение) + интеграция-источник -> действие в кассе (создать чек/заказ)
    по шаблону, с сопоставлением полей для CRM.
    GET ?company_id= - список (со статистикой заданий журнала)
    POST {company_id, name, trigger_type, source_integration_id, action_type,
          action_template, target_integration_id, field_mapping} - создать (остановлен)
    PUT {id, company_id, ...те же поля} - изменить; {id, company_id, status} - запустить/остановить
    POST {action: copy, company_id, id, target_company_id, user_id, name?} - копия в другую компанию
    DELETE {id, company_id} - удалить
    '''
    denied = guard(event)
    if denied:
        return denied

    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    params = event.get('queryStringParameters') or {}
    body = json.loads(event.get('body') or '{}') if method != 'GET' else {}
    company_id = params.get('company_id') or body.get('company_id')
    if not company_id:
        return respond(400, {'error': 'company_id required'})

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        if method == 'GET':
            cur.execute(f'''
                SELECT s.id, s.name, s.trigger_type, s.source_integration_id, si.integration_name,
                       s.action_type, s.action_template, s.target_integration_id, ti.integration_name,
                       s.field_mapping, s.status, s.created_at, s.updated_at,
                       COUNT(j.id), COUNT(j.id) FILTER (WHERE j.status = 'error'), MAX(j.created_at),
                       MAX(t.name), s.correction_settings
                FROM {SCHEMA}.automation_scenarios s
                LEFT JOIN {SCHEMA}.automation_action_templates t ON t.code = s.action_template
                LEFT JOIN {SCHEMA}.user_integrations si ON si.id = s.source_integration_id
                LEFT JOIN {SCHEMA}.user_integrations ti ON ti.id = s.target_integration_id
                LEFT JOIN {SCHEMA}.automation_jobs j ON j.scenario_id = s.id
                WHERE s.company_id = %s AND s.removed_at IS NULL
                GROUP BY s.id, si.integration_name, ti.integration_name
                ORDER BY s.created_at DESC
            ''', (company_id,))
            scenarios = [{
                'id': r[0], 'name': r[1], 'trigger_type': r[2],
                'source_integration_id': r[3], 'source_integration_name': r[4],
                'action_type': r[5], 'action_template': r[6],
                'target_integration_id': r[7], 'target_integration_name': r[8],
                'field_mapping': r[9] or {}, 'status': r[10],
                'created_at': r[11], 'updated_at': r[12],
                'jobs_total': r[13], 'jobs_errors': r[14], 'last_job_at': r[15],
                'action_template_name': r[16], 'correction_settings': r[17] or {}
            } for r in cur.fetchall()]
            return respond(200, {'success': True, 'scenarios': scenarios})

        if method == 'POST' and body.get('action') == 'copy':
            result = copy_to_company(cur, conn, int(company_id), body)
            return respond(result['status'], result['body'])

        if method == 'POST':
            error = validate(cur, company_id, body)
            if error:
                return respond(400, {'error': error})
            # Лимит автоматизаций (сценариев) по тарифу; пусто - без ограничения.
            cur.execute(f'''
                SELECT t.max_automations,
                       (SELECT COUNT(*) FROM {SCHEMA}.automation_scenarios a
                        WHERE a.company_id = %s AND a.removed_at IS NULL)
                FROM {SCHEMA}.subscriptions s JOIN {SCHEMA}.tariffs t ON t.id = s.tariff_id
                WHERE s.company_id = %s
            ''', (company_id, company_id))
            limit_row = cur.fetchone()
            if limit_row and limit_row[0] is not None and limit_row[1] >= limit_row[0]:
                return respond(403, {
                    'error': f'Лимит автоматизаций по тарифу исчерпан ({limit_row[0]}). Смените тариф или удалите ненужный сценарий.',
                    'error_code': 'limit_reached'
                })
            cur.execute(f'''
                INSERT INTO {SCHEMA}.automation_scenarios
                    (company_id, name, trigger_type, source_integration_id, action_type,
                     action_template, target_integration_id, field_mapping, status, correction_settings)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'stopped', %s)
                RETURNING id
            ''', (
                company_id, body['name'].strip(), body['trigger_type'],
                body.get('source_integration_id') if TRIGGERS[body['trigger_type']] else None,
                body['action_type'], body['action_template'], body['target_integration_id'],
                json.dumps(body.get('field_mapping') or {}),
                json.dumps(clean_correction(body.get('correction_settings')), ensure_ascii=False)
            ))
            new_id = cur.fetchone()[0]
            conn.commit()
            return respond(200, {'success': True, 'id': new_id})

        scenario_id = body.get('id')
        if not scenario_id:
            return respond(400, {'error': 'id required'})

        if method == 'PUT':
            if set(body.keys()) <= {'id', 'company_id', 'status'}:
                if body.get('status') not in STATUSES:
                    return respond(400, {'error': 'Некорректный статус'})
                cur.execute(f'''
                    UPDATE {SCHEMA}.automation_scenarios SET status = %s, updated_at = NOW()
                    WHERE id = %s AND company_id = %s AND removed_at IS NULL RETURNING id
                ''', (body['status'], scenario_id, company_id))
            else:
                error = validate(cur, company_id, body)
                if error:
                    return respond(400, {'error': error})
                cur.execute(f'''
                    UPDATE {SCHEMA}.automation_scenarios SET
                        name = %s, trigger_type = %s, source_integration_id = %s, action_type = %s,
                        action_template = %s, target_integration_id = %s, field_mapping = %s,
                        correction_settings = %s, updated_at = NOW()
                    WHERE id = %s AND company_id = %s AND removed_at IS NULL RETURNING id
                ''', (
                    body['name'].strip(), body['trigger_type'],
                    body.get('source_integration_id') if TRIGGERS[body['trigger_type']] else None,
                    body['action_type'], body['action_template'], body['target_integration_id'],
                    json.dumps(body.get('field_mapping') or {}),
                    json.dumps(clean_correction(body.get('correction_settings')), ensure_ascii=False),
                    scenario_id, company_id
                ))
            if not cur.fetchone():
                conn.rollback()
                return respond(404, {'error': 'Сценарий не найден'})
            conn.commit()
            return respond(200, {'success': True})

        if method == 'DELETE':
            cur.execute(f'''
                UPDATE {SCHEMA}.automation_scenarios SET removed_at = NOW(), status = 'stopped', updated_at = NOW()
                WHERE id = %s AND company_id = %s AND removed_at IS NULL RETURNING id
            ''', (scenario_id, company_id))
            if not cur.fetchone():
                conn.rollback()
                return respond(404, {'error': 'Сценарий не найден'})
            conn.commit()
            return respond(200, {'success': True})

        return respond(405, {'error': 'Method not allowed'})
    finally:
        cur.close()
        conn.close()

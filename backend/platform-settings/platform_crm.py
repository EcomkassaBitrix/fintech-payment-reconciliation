'''
CRM платформы (Битрикс24): передача регистраций клиентов Сверки в CRM владельца платформы.

События кладут в очередь platform_crm_events функции auth-phone (register), profile-update (profile)
и companies-create (company). Очередь разбирает process_queue - по сигналу сразу после события,
по шагу планировщика и по кнопке в админке.
  register - контакт (поиск дубля по телефону) + сделка или лид в выбранной воронке/этапе;
             телефон и канал связи - в выбранные поля.
  profile  - обновление ФИО и почты контакта (и лида, если передаём лидами).
  company  - компания с названием и ИНН (реквизит или своё поле), привязка к контакту и сделке/лиду.
Связи «наш объект -> ID в CRM» - в platform_crm_links.
'''
import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = 't_p83864310_fintech_payment_reco'
RETRY_MINUTES = [1, 5, 15, 60]
CHANNEL_LABELS = {'telegram': 'Telegram', 'max': 'MAX', 'whatsapp': 'WhatsApp', 'sms': 'SMS', 'email': 'Email'}
WEBHOOK_RE = re.compile(r'^https://[^/]+/rest/\d+/[A-Za-z0-9]+/?$')


def valid_webhook(url: str) -> Optional[str]:
    url = (url or '').strip()
    if not url:
        return 'Укажите входящий вебхук Битрикс24'
    if 'functions.poehali.dev' in url:
        return 'Это адрес Сверки - сюда нужен входящий вебхук вашего портала Битрикс24'
    if not WEBHOOK_RE.match(url):
        return 'Нужен адрес вида https://ваш-портал.bitrix24.ru/rest/1/код/'
    return None


def call(webhook_url: str, method: str, params: Optional[Dict[str, Any]] = None,
         timeout: float = 2.5) -> Tuple[Any, str]:
    req = urllib.request.Request(
        webhook_url.rstrip('/') + f'/{method}.json',
        data=json.dumps(params or {}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode('utf-8'))
        except Exception:
            return None, f'Битрикс24 ответил HTTP {e.code}'
    except Exception as e:
        return None, f'Битрикс24 недоступен: {str(e)[:120]}'
    if isinstance(payload, dict) and payload.get('error'):
        return None, f"Битрикс24 ({method}): {payload.get('error_description') or payload['error']}"
    return payload.get('result'), ''


def batch(webhook_url: str, cmd: Dict[str, str]) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    result, err = call(webhook_url, 'batch', {'halt': 0, 'cmd': cmd}, timeout=2.5)
    if err:
        return {}, {}, err
    result = result or {}
    res = result.get('result') or {}
    errors = result.get('result_error') or {}
    return (res if isinstance(res, dict) else {}), (errors if isinstance(errors, dict) else {}), ''


# ---------- справочник для настройки ----------

def _field_list(entity: str, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    fields = []
    for code, f in (raw or {}).items():
        if not isinstance(f, dict) or f.get('isReadOnly'):
            continue
        title = f.get('formLabel') or f.get('listLabel') or f.get('title') or code
        item = {'ref': f'{entity}.{code}', 'code': code, 'title': title, 'type': f.get('type'),
                'multiple': bool(f.get('isMultiple')), 'custom': code.startswith('UF_')}
        if isinstance(f.get('items'), list) and f['items']:
            item['items'] = [{'value': str(i.get('ID')), 'label': str(i.get('VALUE') or i.get('ID'))}
                             for i in f['items'] if isinstance(i, dict) and i.get('ID') is not None]
        fields.append(item)
    fields.sort(key=lambda x: (x['custom'], str(x['title']).lower()))
    return fields


def load_reference(webhook_url: str) -> Tuple[Optional[Dict[str, Any]], str]:
    '''Воронки и этапы сделок, статусы лидов, поля сделки/лида/контакта/компании.'''
    cmd = {e: f'crm.{e}.fields' for e in ('deal', 'lead', 'contact', 'company')}
    cmd['categories'] = 'crm.category.list?entityTypeId=2'
    for page in range(6):
        cmd[f'statuses{page}'] = f'crm.status.list?start={page * 50}'
    res, errors, err = batch(webhook_url, cmd)
    if err:
        return None, err
    if not res.get('contact'):
        detail = (errors.get('contact') or {}).get('error_description') or 'у вебхука нет права crm'
        return None, f'Битрикс24 не отдал поля CRM: {detail}'
    categories = {'0': 'Общая воронка'}
    cat_raw = res.get('categories') or {}
    for c in (cat_raw.get('categories') if isinstance(cat_raw, dict) else cat_raw) or []:
        categories[str(c.get('id'))] = c.get('name') or f"Воронка {c.get('id')}"
    seen, deal_stages, lead_stages = set(), [], []
    for page in range(6):
        for s in res.get(f'statuses{page}') or []:
            entity_id = s.get('ENTITY_ID') or ''
            key = (entity_id, s.get('STATUS_ID'))
            if key in seen:
                continue
            seen.add(key)
            item = {'value': s.get('STATUS_ID'), 'label': s.get('NAME'), 'sort': int(s.get('SORT') or 0)}
            if entity_id == 'STATUS':
                lead_stages.append(item)
            elif entity_id.startswith('DEAL_STAGE'):
                cat = entity_id[len('DEAL_STAGE_'):] if entity_id != 'DEAL_STAGE' else '0'
                item['group'] = categories.get(cat, f'Воронка {cat}')
                item['group_id'] = cat
                deal_stages.append(item)
    deal_stages.sort(key=lambda s: (int(s['group_id']) if s['group_id'].isdigit() else 0, s['sort']))
    lead_stages.sort(key=lambda s: s['sort'])
    return {
        'fields': {e: _field_list(e, res.get(e)) for e in ('deal', 'lead', 'contact', 'company')},
        'stages': {'deal': deal_stages, 'lead': lead_stages},
    }, ''


# ---------- настройки и очередь ----------

SETTINGS_COLUMNS = ('webhook_url', 'is_enabled', 'entity', 'stage_id', 'phone_field', 'phone_field_type',
                    'phone_to_contact', 'channel_field', 'channel_field_type', 'inn_field', 'inn_field_type',
                    'title_template', 'channel_map', 'updated_at')


def load_settings(cur) -> Dict[str, Any]:
    cur.execute(f"SELECT {', '.join(SETTINGS_COLUMNS)} FROM {SCHEMA}.platform_crm_settings WHERE id = 1")
    row = cur.fetchone()
    return dict(zip(SETTINGS_COLUMNS, row)) if row else {}


def save_settings(cur, user_id: int, body: Dict[str, Any]) -> Optional[str]:
    webhook = str(body.get('webhook_url') or '').strip()
    if webhook and not webhook.endswith('/'):
        webhook += '/'
    enabled = bool(body.get('is_enabled'))
    if enabled or webhook:
        err = valid_webhook(webhook)
        if err:
            return err
    entity = body.get('entity') if body.get('entity') in ('deal', 'lead') else 'deal'
    stage = str(body.get('stage_id') or '').strip() or None
    if enabled and not stage:
        return 'Выберите воронку и этап, куда класть ' + ('сделки' if entity == 'deal' else 'лиды')
    title = str(body.get('title_template') or '').strip()[:255] or 'Регистрация в Сверке: {name}'
    raw_map = body.get('channel_map') if isinstance(body.get('channel_map'), dict) else {}
    channel_map = {k: str(v)[:100] for k, v in raw_map.items() if k in CHANNEL_LABELS and v not in (None, '')}
    cur.execute(f'''
        UPDATE {SCHEMA}.platform_crm_settings SET
            webhook_url = %s, is_enabled = %s, entity = %s, stage_id = %s,
            phone_field = %s, phone_field_type = %s, phone_to_contact = %s,
            channel_field = %s, channel_field_type = %s, inn_field = %s, inn_field_type = %s,
            title_template = %s, channel_map = %s, updated_at = NOW(), updated_by = %s
        WHERE id = 1
    ''', (webhook or None, enabled, entity, stage,
          str(body.get('phone_field') or 'contact.PHONE')[:150], (str(body.get('phone_field_type') or '')[:50] or None),
          bool(body.get('phone_to_contact', True)),
          (str(body.get('channel_field') or '')[:150] or None), (str(body.get('channel_field_type') or '')[:50] or None),
          str(body.get('inn_field') or 'requisite')[:150], (str(body.get('inn_field_type') or '')[:50] or None),
          title, json.dumps(channel_map), user_id))
    return None


def recent_events(cur, limit: int = 30) -> List[Dict[str, Any]]:
    cur.execute(f'''
        SELECT e.id, e.kind, e.status, e.attempts, e.error, e.result, e.created_at, e.processed_at,
               u.phone, u.full_name, c.name, c.inn
        FROM {SCHEMA}.platform_crm_events e
        LEFT JOIN {SCHEMA}.app_users u ON u.id = e.user_id
        LEFT JOIN {SCHEMA}.companies c ON c.id = e.company_id
        ORDER BY e.id DESC LIMIT %s
    ''', (limit,))
    return [{'id': r[0], 'kind': r[1], 'status': r[2], 'attempts': r[3], 'error': r[4], 'result': r[5],
             'created_at': r[6], 'processed_at': r[7], 'phone': r[8], 'full_name': r[9],
             'company_name': r[10], 'company_inn': r[11]} for r in cur.fetchall()]


def retry_event(cur, event_id: int) -> None:
    cur.execute(f'''
        UPDATE {SCHEMA}.platform_crm_events SET status = 'new', attempts = 0, error = NULL, next_attempt_at = NOW()
        WHERE id = %s
    ''', (event_id,))


# ---------- передача в CRM ----------

def _phone(raw: Any) -> Optional[str]:
    digits = re.sub(r'\D', '', str(raw or ''))
    return f'+{digits}' if digits else None


def _split_name(full_name: str) -> Dict[str, str]:
    parts = (full_name or '').split()
    if len(parts) == 3:
        return {'LAST_NAME': parts[0], 'NAME': parts[1], 'SECOND_NAME': parts[2]}
    return {'NAME': ' '.join(parts)} if parts else {}


def _field_value(field_type: Optional[str], value: Any, items: Optional[List[Dict[str, Any]]] = None) -> Any:
    '''Значение под тип поля: мультиполе телефона, список (ID варианта по названию), строка.'''
    if field_type == 'crm_multifield':
        return [{'VALUE': value, 'VALUE_TYPE': 'WORK'}]
    if field_type == 'enumeration' and items:
        text = str(value or '').strip().lower()
        for i in items:
            if str(i.get('label') or '').strip().lower() == text:
                return i['value']
        for i in items:
            if text and text in str(i.get('label') or '').lower():
                return i['value']
        return None
    return value


def _ref(ref: Optional[str]) -> Tuple[str, str]:
    if not ref or '.' not in ref:
        return '', ''
    obj, _, code = ref.partition('.')
    return obj, code


def _link(cur, object_type: str, object_id: int) -> Dict[str, Any]:
    cur.execute(f'''
        SELECT crm_contact_id, crm_entity, crm_entity_id, crm_company_id
        FROM {SCHEMA}.platform_crm_links WHERE object_type = %s AND object_id = %s
    ''', (object_type, object_id))
    r = cur.fetchone()
    return {'contact': r[0], 'entity': r[1], 'entity_id': r[2], 'company': r[3]} if r else {}


def _save_link(cur, object_type: str, object_id: int, **values: Any) -> None:
    cols = {'contact': 'crm_contact_id', 'entity': 'crm_entity', 'entity_id': 'crm_entity_id', 'company': 'crm_company_id'}
    data = {cols[k]: (str(v) if v is not None else None) for k, v in values.items() if k in cols}
    if not data:
        return
    names = list(data)
    cur.execute(f'''
        INSERT INTO {SCHEMA}.platform_crm_links (object_type, object_id, {', '.join(names)})
        VALUES (%s, %s, {', '.join(['%s'] * len(names))})
        ON CONFLICT (object_type, object_id) DO UPDATE SET
            {', '.join(f'{n} = COALESCE(EXCLUDED.{n}, platform_crm_links.{n})' for n in names)}, updated_at = NOW()
    ''', (object_type, object_id, *data.values()))


def _user(cur, user_id: int) -> Optional[Dict[str, Any]]:
    cur.execute(f'SELECT id, phone, full_name, email FROM {SCHEMA}.app_users WHERE id = %s', (user_id,))
    r = cur.fetchone()
    return {'id': r[0], 'phone': r[1], 'full_name': r[2] or '', 'email': r[3] or ''} if r else None


def _enum_items(webhook: str, cache: Dict[str, Any], obj: str, code: str) -> Optional[List[Dict[str, Any]]]:
    key = f'{obj}.{code}'
    if key not in cache:
        raw, _ = call(webhook, f'crm.{obj}.fields')
        cache[key] = next((f.get('items') for f in _field_list(obj, raw or {}) if f['code'] == code), None)
    return cache[key]


def _extra_fields(settings: Dict[str, Any], target: str, phone: Optional[str], channel: Optional[str],
                  webhook: str, cache: Dict[str, Any], channel_key: Optional[str] = None) -> Dict[str, Any]:
    fields = _extra_fields_base(settings, target, phone, channel, webhook, cache)
    obj, code = _ref(settings.get('channel_field'))
    mapped = (settings.get('channel_map') or {}).get(channel_key or '')
    if mapped and obj == target and code and settings.get('channel_field_type') == 'enumeration':
        fields[code] = mapped
    return fields


def _extra_fields_base(settings: Dict[str, Any], target: str, phone: Optional[str], channel: Optional[str],
                  webhook: str, cache: Dict[str, Any]) -> Dict[str, Any]:
    '''Поля «телефон» и «канал связи», которые выбраны для объекта target (contact / deal / lead).'''
    fields: Dict[str, Any] = {}
    obj, code = _ref(settings.get('phone_field'))
    if phone and obj == target and code:
        fields[code] = _field_value(settings.get('phone_field_type') or ('crm_multifield' if code == 'PHONE' else None), phone)
    obj, code = _ref(settings.get('channel_field'))
    if channel and obj == target and code:
        ftype = settings.get('channel_field_type')
        items = _enum_items(webhook, cache, obj, code) if ftype == 'enumeration' else None
        value = _field_value(ftype, channel, items)
        if value is not None:
            fields[code] = value
    return fields


def _find_contact(webhook: str, phone: Optional[str]) -> Optional[str]:
    if not phone:
        return None
    res, err = call(webhook, 'crm.duplicate.findbycomm', {'entity_type': 'CONTACT', 'type': 'PHONE', 'values': [phone]})
    ids = (res or {}).get('CONTACT') if isinstance(res, dict) else None
    return str(ids[0]) if ids else None


def handle_register(cur, webhook: str, settings: Dict[str, Any], event: Dict[str, Any],
                    cache: Dict[str, Any]) -> Dict[str, Any]:
    user = _user(cur, event['user_id'])
    if not user:
        raise RuntimeError('Пользователь не найден')
    link = _link(cur, 'user', user['id'])
    phone = _phone(user['phone'])
    channel_key = str((event.get('payload') or {}).get('channel') or '')
    channel = CHANNEL_LABELS.get(channel_key, channel_key or None)
    result: Dict[str, Any] = {}

    contact_id = link.get('contact')
    if not contact_id:
        contact_id = _find_contact(webhook, phone)
        result['contact_found'] = bool(contact_id)
    contact_fields = _split_name(user['full_name']) or {'NAME': f'Клиент {phone or ""}'.strip()}
    if user['email']:
        contact_fields['EMAIL'] = [{'VALUE': user['email'], 'VALUE_TYPE': 'WORK'}]
    if settings.get('phone_to_contact') and phone:
        contact_fields['PHONE'] = [{'VALUE': phone, 'VALUE_TYPE': 'WORK'}]
    contact_fields.update(_extra_fields(settings, 'contact', phone, channel, webhook, cache, channel_key))
    if not contact_id:
        contact_fields.setdefault('SOURCE_DESCRIPTION', 'Регистрация в Сверке')
        new_id, err = call(webhook, 'crm.contact.add', {'fields': contact_fields})
        if err:
            raise RuntimeError(err)
        contact_id = str(new_id)
        result['contact_created'] = True
    _save_link(cur, 'user', user['id'], contact=contact_id)
    result['contact_id'] = contact_id

    if link.get('entity_id'):
        result['entity_id'] = link['entity_id']
        return result

    entity = settings.get('entity') or 'deal'
    name = user['full_name'] or phone or f"#{user['id']}"
    title = str(settings.get('title_template') or 'Регистрация в Сверке: {name}').replace('{name}', name).replace('{phone}', phone or '')
    fields: Dict[str, Any] = {'TITLE': title[:255], 'CONTACT_ID': contact_id,
                              'SOURCE_DESCRIPTION': 'Регистрация в Сверке'}
    stage = str(settings.get('stage_id') or '')
    if entity == 'deal':
        fields['STAGE_ID'] = stage
        m = re.match(r'^C(\d+):', stage)
        fields['CATEGORY_ID'] = m.group(1) if m else '0'
    else:
        fields['STATUS_ID'] = stage
        fields.update(_split_name(user['full_name']))
        if phone:
            fields['PHONE'] = [{'VALUE': phone, 'VALUE_TYPE': 'WORK'}]
        if user['email']:
            fields['EMAIL'] = [{'VALUE': user['email'], 'VALUE_TYPE': 'WORK'}]
    fields.update(_extra_fields(settings, entity, phone, channel, webhook, cache, channel_key))
    new_id, err = call(webhook, f'crm.{entity}.add', {'fields': fields})
    if err:
        raise RuntimeError(err)
    _save_link(cur, 'user', user['id'], entity=entity, entity_id=new_id)
    result.update({'entity': entity, 'entity_id': str(new_id)})
    return result


def _update_multi(webhook: str, obj: str, obj_id: str, code: str, value: str, current: Any) -> Optional[str]:
    '''Заменяет первое значение мультиполя (почта): есть - меняем по ID, нет - добавляем.'''
    items = current if isinstance(current, list) else []
    if any(str(i.get('VALUE') or '').lower() == value.lower() for i in items if isinstance(i, dict)):
        return None
    first = next((i for i in items if isinstance(i, dict) and i.get('ID')), None)
    new = [{'ID': first['ID'], 'VALUE': value, 'VALUE_TYPE': first.get('VALUE_TYPE') or 'WORK'}] if first \
        else [{'VALUE': value, 'VALUE_TYPE': 'WORK'}]
    _, err = call(webhook, f'crm.{obj}.update', {'id': obj_id, 'fields': {code: new}})
    return err or None


def handle_profile(cur, webhook: str, settings: Dict[str, Any], event: Dict[str, Any],
                   cache: Dict[str, Any]) -> Dict[str, Any]:
    user = _user(cur, event['user_id'])
    if not user:
        raise RuntimeError('Пользователь не найден')
    link = _link(cur, 'user', user['id'])
    if not link.get('contact'):
        # Регистрация ещё не передана (CRM подключили позже) - передаём сразу с актуальными данными.
        return {'via_register': True, **handle_register(cur, webhook, settings, event, cache)}
    result: Dict[str, Any] = {'contact_id': link['contact']}
    targets = [('contact', link['contact'])]
    if link.get('entity') == 'lead' and link.get('entity_id'):
        targets.append(('lead', link['entity_id']))
    for obj, obj_id in targets:
        current, err = call(webhook, f'crm.{obj}.get', {'id': obj_id})
        if err:
            raise RuntimeError(err)
        fields = _split_name(user['full_name'])
        fields = {k: v for k, v in fields.items() if str((current or {}).get(k) or '') != v}
        if fields:
            _, err = call(webhook, f'crm.{obj}.update', {'id': obj_id, 'fields': fields})
            if err:
                raise RuntimeError(err)
            result[f'{obj}_name'] = True
        if user['email']:
            err = _update_multi(webhook, obj, obj_id, 'EMAIL', user['email'], (current or {}).get('EMAIL'))
            if err:
                raise RuntimeError(err)
            result[f'{obj}_email'] = True
    return result


def _requisite_preset(webhook: str, inn: str, cache: Dict[str, Any]) -> Optional[str]:
    if 'presets' not in cache:
        res, _ = call(webhook, 'crm.requisite.preset.list', {'select': ['ID', 'NAME', 'ACTIVE']})
        cache['presets'] = [p for p in (res or []) if isinstance(p, dict) and p.get('ACTIVE') != 'N']
    presets = cache['presets']
    want = ('ип', 'индивидуал') if len(inn) == 12 else ('организац', 'юр', 'ооо')
    for p in presets:
        if any(w in str(p.get('NAME') or '').lower() for w in want):
            return str(p['ID'])
    return str(presets[0]['ID']) if presets else None


def handle_company(cur, webhook: str, settings: Dict[str, Any], event: Dict[str, Any],
                   cache: Dict[str, Any]) -> Dict[str, Any]:
    cur.execute(f'SELECT id, name, inn, kpp, ogrn, full_name, created_by FROM {SCHEMA}.companies WHERE id = %s',
                (event['company_id'],))
    row = cur.fetchone()
    if not row:
        raise RuntimeError('Компания не найдена')
    company = {'id': row[0], 'name': row[1], 'inn': (row[2] or '').strip(), 'kpp': row[3], 'ogrn': row[4],
               'full_name': row[5]}
    user_id = event.get('user_id') or row[6]
    user_link = _link(cur, 'user', user_id) if user_id else {}
    if user_id and not user_link.get('contact'):
        handle_register(cur, webhook, settings, {**event, 'user_id': user_id}, cache)
        user_link = _link(cur, 'user', user_id)
    result: Dict[str, Any] = {}

    crm_company = _link(cur, 'company', company['id']).get('company')
    if not crm_company:
        fields: Dict[str, Any] = {'TITLE': company['name'][:255], 'SOURCE_DESCRIPTION': 'Регистрация в Сверке'}
        obj, code = _ref(settings.get('inn_field'))
        if company['inn'] and obj == 'company' and code:
            fields[code] = company['inn']
        if user_link.get('contact'):
            fields['CONTACT_ID'] = user_link['contact']
        new_id, err = call(webhook, 'crm.company.add', {'fields': fields})
        if err:
            raise RuntimeError(err)
        crm_company = str(new_id)
        _save_link(cur, 'company', company['id'], company=crm_company)
        result['company_created'] = True
        if company['inn'] and (settings.get('inn_field') or 'requisite') == 'requisite':
            preset = _requisite_preset(webhook, company['inn'], cache)
            req_fields = {'ENTITY_TYPE_ID': 4, 'ENTITY_ID': crm_company, 'PRESET_ID': preset,
                          'NAME': (company['full_name'] or company['name'])[:150], 'RQ_INN': company['inn']}
            if company['kpp']:
                req_fields['RQ_KPP'] = company['kpp']
            if company['ogrn']:
                req_fields['RQ_OGRNIP' if len(company['inn']) == 12 else 'RQ_OGRN'] = company['ogrn']
            if len(company['inn']) == 10:
                req_fields['RQ_COMPANY_NAME'] = (company['full_name'] or company['name'])[:255]
            _, err = call(webhook, 'crm.requisite.add', {'fields': req_fields})
            result['requisite'] = 'ok' if not err else err
    result['company_id'] = crm_company

    if user_link.get('entity_id') and user_link.get('entity') == 'deal':
        _, err = call(webhook, 'crm.deal.update', {'id': user_link['entity_id'], 'fields': {'COMPANY_ID': crm_company}})
        result['deal_linked'] = not err
    elif user_link.get('entity_id') and user_link.get('entity') == 'lead':
        _, err = call(webhook, 'crm.lead.update', {'id': user_link['entity_id'],
                                                   'fields': {'COMPANY_ID': crm_company, 'COMPANY_TITLE': company['name'][:255]}})
        result['lead_linked'] = not err
    elif user_link.get('contact'):
        call(webhook, 'crm.contact.company.add', {'id': user_link['contact'], 'fields': {'COMPANY_ID': crm_company}})
    return result


HANDLERS = {'register': handle_register, 'profile': handle_profile, 'company': handle_company}


def process_queue(cur, conn, budget_sec: float = 1.8) -> Dict[str, int]:
    '''Разбор очереди событий по порядку, пока есть время. Повторы: 1, 5, 15, 60 минут.'''
    settings = load_settings(cur)
    stats = {'done': 0, 'failed': 0, 'skipped': 0}
    if not settings.get('is_enabled') or not settings.get('webhook_url'):
        return stats
    webhook = settings['webhook_url']
    started = time.time()
    cache: Dict[str, Any] = {}
    while time.time() - started < budget_sec:
        cur.execute(f'''
            SELECT id, kind, user_id, company_id, attempts, payload FROM {SCHEMA}.platform_crm_events
            WHERE status IN ('new', 'retry') AND next_attempt_at <= NOW()
            ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED
        ''')
        r = cur.fetchone()
        if not r:
            break
        event = {'id': r[0], 'kind': r[1], 'user_id': r[2], 'company_id': r[3], 'attempts': r[4], 'payload': r[5] or {}}
        handler = HANDLERS.get(event['kind'])
        try:
            if not handler:
                raise RuntimeError(f"Неизвестное событие {event['kind']}")
            result = handler(cur, webhook, settings, event, cache)
            cur.execute(f'''
                UPDATE {SCHEMA}.platform_crm_events SET status = 'done', attempts = attempts + 1, error = NULL,
                    result = %s, processed_at = NOW() WHERE id = %s
            ''', (json.dumps(result, ensure_ascii=False), event['id']))
            stats['done'] += 1
        except Exception as e:
            attempts = event['attempts'] + 1
            final = attempts > len(RETRY_MINUTES)
            delay = RETRY_MINUTES[min(attempts - 1, len(RETRY_MINUTES) - 1)]
            cur.execute(f'''
                UPDATE {SCHEMA}.platform_crm_events SET status = %s, attempts = %s, error = %s,
                    next_attempt_at = NOW() + make_interval(mins => %s), processed_at = NOW()
                WHERE id = %s
            ''', ('failed' if final else 'retry', attempts, str(e)[:500], delay, event['id']))
            stats['failed'] += 1
        conn.commit()
    return stats


def pending_count(cur) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {SCHEMA}.platform_crm_events WHERE status IN ('new', 'retry')")
    return int(cur.fetchone()[0])

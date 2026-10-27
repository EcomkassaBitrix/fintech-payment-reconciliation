import json
import re
import os
import socket
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from auth_guard import guard, internal_headers, BLOCKED_COMPANIES_SQL
import platform_crm

SCHEMA = 't_p83864310_fintech_payment_reco'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Cron-Token',
    'Access-Control-Max-Age': '86400'
}

# Фоновые задачи по каждой компании - то, что сейчас запускается входом в
# кабинет и открытием страниц. При включённом cron их вызывает планировщик.
JOBS_URL = 'https://functions.poehali.dev/22902813-812b-495a-9ea0-8497b880c461'
RESYNC_URL = 'https://functions.poehali.dev/0b50cd7c-94bc-4be9-824a-0bb119c6adef'
# Компаний за шаг: все задачи шага стартуют одновременно, у базы ограничено число подключений.
TICK_BATCH = 3
TASK_STAGGER_SEC = 0.3
TASK_STAGGER_TOTAL_SEC = 2.0
# Сервис отправки сообщений в мессенджеры и писем (если в настройках не задан свой адрес).
DEFAULT_MESSENGER_URL = 'https://functions.poehali.dev/ace36e55-b169-41f2-9d2b-546f92221bb7'
FETCH_ORDERS_URL = 'https://functions.poehali.dev/dc01171b-cd60-4a98-b96c-5d167bc1add8'
# Окно авто-дозагрузки Екомкассы: документы, обновлённые за последние N часов.
ECOMKASSA_AUTO_HOURS = 24
# Запас окна поиска пропущенных платежей/чеков от прошлого успешного поиска, мин.
ECOMKASSA_SEARCH_OVERLAP_MIN = 5
OFD_URL = 'https://functions.poehali.dev/c7fad594-b60b-47fb-8f73-31b629f1e0a2'
# Ежедневная проверка «платежи без чека за вчера» (backend/notifications, action=dispatch, daily).
NOTIFICATIONS_URL = 'https://functions.poehali.dev/8f4541fc-6ff8-4816-a954-324e4278743d'
BANK_URL = 'https://functions.poehali.dev/916892e2-fd4d-4106-8d92-a95be195aa99'
SELF_URL = 'https://functions.poehali.dev/9e410f34-57f5-40ff-85f6-ccc802b812d9'
SUBSCRIPTION_URL = 'https://functions.poehali.dev/51f17dfc-af76-4415-a5cc-329b1ddaaa8c'

# Источники, которые планировщик загружает сам. Админ включает/выключает каждый
# (platform_settings.cron_sources: {key: bool}); нет записи - включён.
CRON_SOURCES = [
    {'key': 'ecomkassa', 'unit': 'документов', 'name': 'Екомкасса: новые счета, заказы и чеки',
     'hint': 'Не нужно, когда настроены вебхуки Екомкассы по платежам'},
    {'key': 'ecomkassa_receipts', 'unit': 'чеков', 'name': 'Екомкасса: дозагрузка непробитых чеков',
     'hint': 'Довязывает чек к платежу шлюза и ищет в кассе оплаченные документы с прошлой загрузки - страховка от потерянных вебхуков'},
    {'key': 'ofd', 'unit': 'чеков', 'name': 'ОФД: чеки', 'hint': 'Всё новое с прошлой загрузки'},
    {'key': 'bank', 'unit': 'операций', 'name': 'Банки: выписки',
     'hint': 'Если клиент задал частоту в настройках интеграции - берётся она'},
    {'key': 'automation', 'unit': 'заданий', 'name': 'Автоматизация и уведомления',
     'hint': 'Очередь сценариев, повторы, рассылка уведомлений, «платежи без чека»'},
    {'key': 'subscriptions', 'unit': 'списаний', 'name': 'Подписки: автосписание по картам',
     'hint': 'Продление подписок с включённым автопродлением по сохранённой карте Т‑Банка. «Раз в день» - после полуночи по Москве'},
]
# Частота запуска источника планировщиком (админ выбирает пресет), минуты.
INTERVAL_PRESETS = {'cron': 0, '1h': 60, '12h': 720, '1d': 1440}
# По умолчанию - как работало до настройки: банк раз в час, остальное каждый запуск.
DEFAULT_INTERVALS = {'ecomkassa': 'cron', 'ecomkassa_receipts': 'cron', 'ofd': 'cron', 'bank': '1h', 'automation': 'cron',
                     'subscriptions': 'cron'}


def source_interval(settings: Dict[str, Any], key: str) -> str:
    value = (settings.get('cron_intervals') or {}).get(key)
    return value if value in INTERVAL_PRESETS else DEFAULT_INTERVALS.get(key, 'cron')


def source_minutes(settings: Dict[str, Any], key: str) -> int:
    # Запас 2 минуты: запуск крона приходит чуть раньше/позже - не пропускаем лишний цикл.
    m = INTERVAL_PRESETS[source_interval(settings, key)]
    return max(0, m - 2)


def company_midnight_utc(zone_name: Optional[str]) -> datetime:
    '''Начало текущих суток компании (00:00 по её часовому поясу) в UTC без tzinfo, как в базе.'''
    try:
        zone = ZoneInfo(zone_name or 'Europe/Moscow')
    except Exception:
        zone = ZoneInfo('Europe/Moscow')
    local_now = datetime.now(dt_timezone.utc).astimezone(zone)
    midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(dt_timezone.utc).replace(tzinfo=None)


def daily_due(cur, source: str, company_ids: List[int]) -> List[int]:
    '''
    «Раз в день» = после полуночи по часовому поясу компании: источник ещё не запускался
    планировщиком с 00:00 текущих суток компании. Первый запуск крона после полуночи его и берёт.
    '''
    if not company_ids:
        return []
    cur.execute(f'''
        SELECT c.id, c.timezone,
               (SELECT MAX(r.finished_at) FROM {SCHEMA}.cron_source_runs r WHERE r.source = %s AND r.company_id = c.id)
        FROM {SCHEMA}.companies c WHERE c.id = ANY(%s)
    ''', (source, company_ids))
    return [cid for cid, zone, last in cur.fetchall() if last is None or last < company_midnight_utc(zone)]


def due_companies(cur, source: str, company_ids: List[int], minutes: int) -> List[int]:
    '''Компании, у которых с прошлого запуска источника планировщиком прошло не меньше minutes.'''
    if minutes >= INTERVAL_PRESETS['1d'] - 2:
        return daily_due(cur, source, company_ids)
    if not minutes or not company_ids:
        return list(company_ids)
    cur.execute(f'''
        SELECT company_id FROM {SCHEMA}.cron_source_runs
        WHERE source = %s AND company_id = ANY(%s) AND finished_at > NOW() - make_interval(mins => %s)
    ''', (source, company_ids, minutes))
    recent = {r[0] for r in cur.fetchall()}
    return [c for c in company_ids if c not in recent]


def subscriptions_due(cur, settings: Dict[str, Any]) -> bool:
    '''Пора ли запускать автосписание: по частоте из настроек; «раз в день» - после полуночи по Москве.
    Если прошлый запуск не успел всех (error = pending) - продолжаем сразу.'''
    interval = source_interval(settings, 'subscriptions')
    if interval == 'cron':
        return True
    cur.execute(f'''SELECT finished_at, error FROM {SCHEMA}.cron_source_runs
                    WHERE source = 'subscriptions' AND company_id = 0 AND item_key = '' ''')
    row = cur.fetchone()
    if not row or row[1] == 'pending':
        return True
    if interval == '1d':
        return row[0] < company_midnight_utc('Europe/Moscow')
    return row[0] < datetime.utcnow() - timedelta(minutes=source_minutes(settings, 'subscriptions'))


SOURCE_PROVIDERS = {'ecomkassa': ['ecomkassa'], 'ecomkassa_receipts': ['ecomkassa_gateway'],
                    'ofd': ['ofdru'], 'bank': ['tbank_account', 'tochka_account']}


def source_on(settings: Dict[str, Any], key: str) -> bool:
    return (settings.get('cron_sources') or {}).get(key, True) is not False


def cron_sources_view(cur, settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    '''Источники с отметкой вкл/выкл и подключёнными интеграциями (компания, название, последняя загрузка).'''
    cur.execute(f'''
        SELECT p.slug, ui.id, ui.integration_name, c.name, ui.last_synced_at
        FROM {SCHEMA}.user_integrations ui
        JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        JOIN {SCHEMA}.companies c ON c.id = ui.company_id
        WHERE ui.status = 'active' AND c.status = 'active'
        ORDER BY c.name, ui.integration_name
    ''')
    by_slug: Dict[str, List[Dict[str, Any]]] = {}
    for slug, iid, name, company, last in cur.fetchall():
        by_slug.setdefault(slug, []).append({'id': iid, 'name': name, 'company': company,
                                             'last_synced_at': last.isoformat() if last else None})
    # Последний запуск каждого источника планировщиком - сумма по всем клиентам.
    cur.execute(f'''
        WITH last AS (SELECT source, MAX(tick) tick FROM {SCHEMA}.cron_source_runs GROUP BY source)
        SELECT r.source, SUM(r.loaded), COUNT(*), COUNT(r.error) FILTER (WHERE r.error <> 'pending'), MAX(r.finished_at),
               (ARRAY_AGG(r.error) FILTER (WHERE r.error IS NOT NULL AND r.error <> 'pending'))[1],
               COUNT(*) FILTER (WHERE r.error = 'pending')
        FROM {SCHEMA}.cron_source_runs r JOIN last l ON l.source = r.source AND l.tick = r.tick
        GROUP BY r.source
    ''')
    runs = {r[0]: {'loaded': int(r[1] or 0), 'calls': r[2], 'failed': r[3],
                   'finished_at': r[4].isoformat() if r[4] else None, 'error': r[5], 'pending': r[6]} for r in cur.fetchall()}
    # Ошибки за последние сутки по каждой задаче - из истории запусков (последняя ошибка и её текст).
    cur.execute(f'''
        SELECT source, COUNT(*), COUNT(*) FILTER (WHERE error IS NOT NULL),
               (ARRAY_AGG(error ORDER BY finished_at DESC) FILTER (WHERE error IS NOT NULL))[1],
               MAX(finished_at) FILTER (WHERE error IS NOT NULL)
        FROM {SCHEMA}.cron_run_history
        WHERE finished_at > NOW() - INTERVAL '1 day'
        GROUP BY source
    ''')
    day = {r[0]: {'runs': r[1], 'errors': r[2], 'last_error': r[3],
                  'last_error_at': r[4].isoformat() if r[4] else None} for r in cur.fetchall()}
    out = []
    for src in CRON_SOURCES:
        integrations = [i for slug in SOURCE_PROVIDERS.get(src['key'], []) for i in by_slug.get(slug, [])]
        out.append({**src, 'enabled': source_on(settings, src['key']), 'interval': source_interval(settings, src['key']),
                    'integrations': integrations,
                    'last_run': runs.get(src['key']),
                    'day_stats': day.get(src['key'], {'runs': 0, 'errors': 0, 'last_error': None, 'last_error_at': None})})
    return out

# Интервал (мин) для внешнего планировщика - показывается в админке.
CRON_INTERVAL_MIN = 1
# Тревога «планировщик не запускался» - если тишина дольше этого (задание на сервере ходит раз в 15 мин).
CRON_STALE_MIN = 20


def automation_queue_view(cur) -> Dict[str, Any]:
    '''
    Состояние очереди автоматизации по всем компаниям (для админки):
    ждут запуска, ждут повтора, в работе, зависли (в работе дольше блокировки), не удалось за сутки.
    Плюс компании с зависшими / проваленными заданиями - чтобы сразу видеть, где проблема.
    '''
    cur.execute(f'''
        SELECT
            COUNT(*) FILTER (WHERE status = 'new' AND next_attempt_at <= NOW()),
            COUNT(*) FILTER (WHERE status = 'error'),
            COUNT(*) FILTER (WHERE status = 'processing' AND locked_until >= NOW()),
            COUNT(*) FILTER (WHERE status = 'processing' AND (locked_until IS NULL OR locked_until < NOW())),
            COUNT(*) FILTER (WHERE status = 'failed' AND updated_at > NOW() - INTERVAL '1 day'),
            MIN(next_attempt_at) FILTER (WHERE status IN ('new', 'error'))
        FROM {SCHEMA}.automation_jobs
        WHERE status IN ('new', 'error', 'processing', 'failed')
    ''')
    r = cur.fetchone()
    cur.execute(f'''
        SELECT c.id, c.name,
               COUNT(*) FILTER (WHERE j.status = 'processing' AND (j.locked_until IS NULL OR j.locked_until < NOW())),
               COUNT(*) FILTER (WHERE j.status = 'failed' AND j.updated_at > NOW() - INTERVAL '1 day'),
               COUNT(*) FILTER (WHERE j.status = 'error')
        FROM {SCHEMA}.automation_jobs j
        JOIN {SCHEMA}.companies c ON c.id = j.company_id
        WHERE j.status = 'processing' AND (j.locked_until IS NULL OR j.locked_until < NOW())
           OR j.status = 'failed' AND j.updated_at > NOW() - INTERVAL '1 day'
           OR j.status = 'error'
        GROUP BY c.id, c.name
        ORDER BY 3 DESC, 4 DESC, 5 DESC
        LIMIT 10
    ''')
    companies = [{'id': x[0], 'name': x[1], 'stuck': x[2], 'failed': x[3], 'retry': x[4]} for x in cur.fetchall()]
    return {'waiting': r[0], 'retry': r[1], 'processing': r[2], 'stuck': r[3], 'failed_day': r[4],
            'oldest_due': r[5].isoformat() if r[5] else None, 'companies': companies}


def respond(status: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {**CORS_HEADERS, 'Content-Type': 'application/json'},
        'body': json.dumps(payload, ensure_ascii=False, default=str),
        'isBase64Encoded': False
    }


def is_admin(cur, user_id) -> bool:
    cur.execute(f'''
        SELECT 1 FROM {SCHEMA}.company_users cu
        JOIN {SCHEMA}.companies c ON c.id = cu.company_id
        WHERE cu.user_id = %s AND cu.status = 'active' AND c.is_platform_admin = true
          AND (cu.platform_admin OR cu.role_id IN (SELECT id FROM {SCHEMA}.roles WHERE slug = 'owner'))
    ''', (user_id,))
    return cur.fetchone() is not None


def load_settings(cur) -> Dict[str, Any]:
    cur.execute(f'''
        SELECT s.managing_company_id, c.name, c.inn, s.cron_enabled, s.cron_token,
               s.cron_last_tick_at, s.cron_last_result, s.updated_at, s.metrika_counter_id, s.cron_sources, s.cron_intervals,
               s.maintenance_enabled, s.maintenance_message, s.maintenance_until, s.messenger_api_url,
               s.contact_email, s.contact_phone, u.email, u.phone, s.contact_address, c.legal_address, s.metrika_script
        FROM {SCHEMA}.platform_settings s
        LEFT JOIN LATERAL (
            SELECT au.email, au.phone FROM {SCHEMA}.company_users cu
            JOIN {SCHEMA}.roles r ON r.id = cu.role_id
            JOIN {SCHEMA}.app_users au ON au.id = cu.user_id
            WHERE cu.company_id = s.managing_company_id AND cu.status = 'active'
            ORDER BY (r.slug = 'owner') DESC, cu.id LIMIT 1
        ) u ON true
        LEFT JOIN {SCHEMA}.companies c ON c.id = s.managing_company_id
        WHERE s.id = 1
    ''')
    r = cur.fetchone()
    return {
        'managing_company_id': r[0], 'managing_company_name': r[1], 'managing_company_inn': r[2],
        'cron_enabled': r[3], 'cron_token': r[4], 'cron_last_tick_at': r[5],
        'cron_last_result': r[6], 'updated_at': r[7], 'metrika_counter_id': r[8], 'cron_sources': r[9] or {}, 'cron_intervals': r[10] or {},
        'maintenance_enabled': bool(r[11]), 'maintenance_message': r[12],
        'maintenance_until': r[13].isoformat() if r[13] else None,
        'messenger_api_url': r[14], 'messenger_api_url_default': DEFAULT_MESSENGER_URL,
        'contact_email': r[15], 'contact_phone': r[16],
        'contact_email_default': r[17], 'contact_phone_default': r[18],
        'contact_address': r[19], 'contact_address_default': r[20],
        'metrika_script': r[21],
    }


def call(url: str, body: Dict[str, Any], timeout: float) -> Optional[str]:
    '''
    Запускает задачу функции, не дожидаясь её конца: тайм-аут ожидания ответа -
    это «задача запущена и работает», а не ошибка. Ошибка - только отказ сразу
    (функция недоступна, ответ с ошибкой).
    '''
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode('utf-8'),
                                     headers={'Content-Type': 'application/json', **internal_headers()}, method='POST')
        urllib.request.urlopen(req, timeout=timeout).close()
        return None
    except (socket.timeout, TimeoutError):
        return None
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            return None
        return str(e)[:200]
    except Exception as e:
        return str(e)[:200]


EXPIRED_NOTICE_HOUR = 9


def subscription_expired(cur) -> List[Tuple[int, int]]:
    '''
    Подписка или пробный период закончились и не продлены: уведомление на следующий день после
    окончания, не раньше 9:00 по часовому поясу компании (опоздавший шаг - до конца второго дня).
    Пояса считаем в коде: функции поясов в SQL платформа запрещает.
    '''
    cur.execute(f'''
        SELECT s.company_id, c.timezone, t.name, s.status = 'trial',
               CASE WHEN s.status = 'trial' THEN s.trial_ends_at ELSE s.current_period_end END AS ends_at
        FROM {SCHEMA}.subscriptions s
        JOIN {SCHEMA}.companies c ON c.id = s.company_id AND c.status = 'active'
        LEFT JOIN {SCHEMA}.tariffs t ON t.id = s.tariff_id
        WHERE CASE WHEN s.status = 'trial' THEN s.trial_ends_at ELSE s.current_period_end END
              BETWEEN NOW() - INTERVAL '4 days' AND NOW()
    ''')
    created: List[Tuple[int, int]] = []
    for company_id, zone, tariff_name, is_trial, ends_at in cur.fetchall():
        try:
            zone_info = ZoneInfo(zone or 'Europe/Moscow')
        except Exception:
            zone_info = ZoneInfo('Europe/Moscow')
        end_day = ends_at.replace(tzinfo=dt_timezone.utc).astimezone(zone_info).date()
        local_now = datetime.now(zone_info)
        if (local_now.date() - end_day).days not in (1, 2):
            continue
        if local_now.date() - end_day == timedelta(days=1) and local_now.hour < EXPIRED_NOTICE_HOUR:
            continue
        entity_id = f'{company_id}:{end_day.isoformat()}'
        what = 'Пробный период' if is_trial else f"Подписка на тариф «{tariff_name or '—'}»"
        cur.execute(f'''
            INSERT INTO {SCHEMA}.notifications (company_id, kind, level, title, message, link_module, entity_type, entity_id, payload)
            SELECT %s, 'subscription_expired', 'error', %s, %s, 'subscription', 'subscription_expired', %s, %s
            WHERE NOT EXISTS (SELECT 1 FROM {SCHEMA}.notifications
                              WHERE kind = 'subscription_expired' AND entity_type = 'subscription_expired' AND entity_id = %s)
            RETURNING id
        ''', (company_id,
              'Пробный период закончился' if is_trial else 'Подписка закончилась',
              f"{what} {'закончился' if is_trial else 'закончилась'} {end_day.strftime('%d.%m.%Y')}"
              f" и не {'продлён' if is_trial else 'продлена'}. "
              'Оплатите подписку, чтобы снова работали сверка, загрузка данных и автоматические чеки.',
              entity_id, json.dumps({'ends_at': ends_at.isoformat()}), entity_id))
        row = cur.fetchone()
        if row:
            created.append((row[0], company_id))
    return created


def subscription_reminders(cur, conn) -> List[int]:
    '''
    Напоминание за 3 дня до конца подписки или пробного периода, если автопродление не сработает
    (выключено или нет карты). Одно на компанию и дату окончания; дубли - в выбранный канал.
    '''
    cur.execute(f'''
        WITH ends AS (
            SELECT s.company_id, t.name AS tariff_name,
                   CASE WHEN s.status = 'trial' THEN s.trial_ends_at ELSE s.current_period_end END AS ends_at,
                   s.status = 'trial' AS is_trial
            FROM {SCHEMA}.subscriptions s
            JOIN {SCHEMA}.companies c ON c.id = s.company_id AND c.status = 'active'
            LEFT JOIN {SCHEMA}.tariffs t ON t.id = s.tariff_id
            WHERE s.status IN ('trial', 'active')
              AND NOT (s.status = 'active' AND s.auto_renew = true AND s.card_id IS NOT NULL)
        )
        INSERT INTO {SCHEMA}.notifications (company_id, kind, level, title, message, link_module, entity_type, entity_id, payload)
        SELECT e.company_id, 'subscription_ending', 'warning',
               CASE WHEN e.is_trial THEN 'Пробный период скоро закончится' ELSE 'Подписка скоро закончится' END,
               CASE WHEN e.is_trial THEN 'Пробный период' ELSE 'Тариф «' || COALESCE(e.tariff_name, '—') || '»' END
               || ' действует до ' || to_char(e.ends_at, 'DD.MM.YYYY')
               || '. Автопродление не включено - оплатите подписку, чтобы сверка и автоматизация не остановились.',
               'subscription', 'subscription_end', e.company_id::text || ':' || to_char(e.ends_at, 'YYYY-MM-DD'),
               jsonb_build_object('ends_at', e.ends_at)
        FROM ends e
        WHERE e.ends_at > NOW() AND e.ends_at < NOW() + INTERVAL '3 days'
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.notifications n
                          WHERE n.kind = 'subscription_ending' AND n.entity_type = 'subscription_end'
                            AND n.entity_id = e.company_id::text || ':' || to_char(e.ends_at, 'YYYY-MM-DD'))
        RETURNING id, company_id
    ''')
    created = cur.fetchall() + subscription_expired(cur)
    for notification_id, company_id in created:
        cur.execute(f'''
            INSERT INTO {SCHEMA}.notification_deliveries (notification_id, user_id, channel)
            SELECT %s, p.user_id, p.channel
            FROM {SCHEMA}.notification_preferences p
            JOIN {SCHEMA}.company_users cu ON cu.company_id = p.company_id AND cu.user_id = p.user_id AND cu.status = 'active'
            WHERE p.company_id = %s AND p.channel IS NOT NULL
            ON CONFLICT (notification_id, user_id) DO NOTHING
        ''', (notification_id, company_id))
    conn.commit()
    return sorted({c for _, c in created})


def tick(cur, conn, settings: Dict[str, Any]) -> Dict[str, Any]:
    '''
    Один шаг планировщика: по каждой компании с активными интеграциями или сценариями
    (пустые компании пропускаются, каждая задача - только если в компании есть её источник) -
    чеки ОФД, банковская выписка (по частоте интеграции), новые документы Екомкассы,
    очередь автоматизации (+ дубли уведомлений и проверка «платежи без чека за
    вчера») и дозагрузка непробитых чеков Екомкассы. Все вызовы параллельно,
    не дожидаясь их окончания. Компаний больше TICK_BATCH - берём по кругу,
    следующая порция - на следующем шаге.
    '''
    tick_started = time.time()
    # Пустые компании (ничего не настроено) пропускаем: нужна хотя бы одна активная
    # интеграция или активный сценарий автоматизации.
    cur.execute(f'''
        SELECT c.id FROM {SCHEMA}.companies c
        WHERE c.status = 'active'
          AND c.id NOT IN ({BLOCKED_COMPANIES_SQL})
          AND (EXISTS (SELECT 1 FROM {SCHEMA}.user_integrations ui
                       WHERE ui.company_id = c.id AND ui.status = 'active')
               OR EXISTS (SELECT 1 FROM {SCHEMA}.automation_scenarios s
                          WHERE s.company_id = c.id AND s.status = 'active' AND s.removed_at IS NULL))
        ORDER BY c.id
    ''')
    all_ids = [r[0] for r in cur.fetchall()]
    offset = int((settings.get('cron_last_result') or {}).get('next_offset') or 0)
    if offset >= len(all_ids):
        offset = 0
    company_ids = all_ids[offset:offset + TICK_BATCH]
    next_offset = offset + TICK_BATCH if offset + TICK_BATCH < len(all_ids) else 0

    ecomkassa_ids = set()
    ecomkassa_due = due_companies(cur, 'ecomkassa', company_ids, source_minutes(settings, 'ecomkassa'))
    if ecomkassa_due and source_on(settings, 'ecomkassa'):
        cur.execute(f'''
            SELECT DISTINCT ui.company_id FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            WHERE p.slug = 'ecomkassa' AND ui.status = 'active' AND ui.company_id = ANY(%s)
        ''', (ecomkassa_due,))
        ecomkassa_ids = {r[0] for r in cur.fetchall()}
    # Окно поиска новых документов - не меньше суток и с запасом больше интервала запуска.
    ecomkassa_hours = max(ECOMKASSA_AUTO_HOURS, INTERVAL_PRESETS[source_interval(settings, 'ecomkassa')] // 60 + 2)
    receipts_due = set(due_companies(cur, 'ecomkassa_receipts', company_ids, source_minutes(settings, 'ecomkassa_receipts')))
    automation_due = set(due_companies(cur, 'automation', company_ids, source_minutes(settings, 'automation')))
    if company_ids:
        # Дозагрузка чеков - только где есть касса Екомкасса.
        cur.execute(f'''
            SELECT DISTINCT ui.company_id FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            WHERE p.slug = 'ecomkassa' AND ui.status = 'active' AND ui.company_id = ANY(%s)
        ''', (company_ids,))
        receipts_due &= {r[0] for r in cur.fetchall()}
        # Автоматизация - только где есть активные сценарии, задачи в очереди или настроены уведомления.
        cur.execute(f'''
            SELECT c.id FROM unnest(%s::int[]) AS c(id)
            WHERE EXISTS (SELECT 1 FROM {SCHEMA}.automation_scenarios s
                          WHERE s.company_id = c.id AND s.status = 'active' AND s.removed_at IS NULL)
               OR EXISTS (SELECT 1 FROM {SCHEMA}.automation_jobs j
                          WHERE j.company_id = c.id AND j.status IN ('new', 'error', 'processing'))
               OR EXISTS (SELECT 1 FROM {SCHEMA}.notification_preferences np WHERE np.company_id = c.id)
        ''', (company_ids,))
        automation_due &= {r[0] for r in cur.fetchall()}
    else:
        receipts_due, automation_due = set(), set()

    ofd_ids = set()
    bank_jobs = []
    if company_ids and source_on(settings, 'ofd'):
        ofd_daily = source_interval(settings, 'ofd') == '1d'
        cur.execute(f'''
            SELECT DISTINCT ui.company_id FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            WHERE p.slug = 'ofdru' AND ui.status = 'active' AND ui.company_id = ANY(%s)
              AND (%s OR ui.last_synced_at IS NULL OR ui.last_synced_at < NOW() - make_interval(mins => %s))
        ''', (company_ids, ofd_daily, source_minutes(settings, 'ofd')))
        ofd_ids = {r[0] for r in cur.fetchall()}
        if ofd_daily:
            ofd_ids &= set(daily_due(cur, 'ofd', list(ofd_ids)))
    if company_ids and source_on(settings, 'bank'):
        # Частота выписки - из настройки интеграции (1 / 12 / 24 часа, по умолчанию 24).
        # «Раз в сутки» = первый запуск после 00:00 по часовому поясу компании.
        # Настройка админки - нижняя граница: чаще неё банк не дёргаем.
        # Последняя попытка = позже из успешной загрузки и запуска кроном (выписка Точки
        # готовится асинхронно, и до её готовности last_synced_at не меняется).
        # Выписка - по календарным дням (Москва): с дня прошлой загрузки (минус день запаса) по сегодня.
        cur.execute(f'''
            SELECT ui.id, ui.company_id,
                   to_char(COALESCE(ui.last_synced_at, NOW() - INTERVAL '3 days') + INTERVAL '3 hours' - INTERVAL '1 day', 'YYYY-MM-DD'),
                   to_char(NOW() + INTERVAL '3 hours', 'YYYY-MM-DD'),
                   COALESCE(ui.sync_interval_hours, 24),
                   GREATEST(ui.last_synced_at, r.finished_at),
                   c.timezone
            FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            JOIN {SCHEMA}.companies c ON c.id = ui.company_id
            LEFT JOIN {SCHEMA}.cron_source_runs r
                   ON r.source = 'bank' AND r.company_id = ui.company_id AND r.item_key = ui.id::text
            WHERE p.slug IN ('tbank_account', 'tochka_account') AND ui.status = 'active' AND ui.company_id = ANY(%s)
        ''', (company_ids,))
        now_utc = datetime.utcnow()
        floor_minutes = source_minutes(settings, 'bank')
        bank_jobs = []
        for ui_id, cid, d_from, d_to, hours, last_try, zone in cur.fetchall():
            if last_try is not None:
                if floor_minutes and last_try > now_utc - timedelta(minutes=floor_minutes):
                    continue
                if hours >= 24:
                    if last_try >= company_midnight_utc(zone):
                        continue
                elif last_try > now_utc - timedelta(minutes=hours * 60 - 2):
                    continue
            bank_jobs.append((ui_id, cid, d_from, d_to))
        if source_interval(settings, 'bank') == '1d' and bank_jobs:
            bank_today = set(daily_due(cur, 'bank', list({j[1] for j in bank_jobs})))
            bank_jobs = [j for j in bank_jobs if j[1] in bank_today]

    # «Платежи без чека за вчера» - раз в сутки после 00:00 по поясу компании, только где есть
    # платёжки (без них таких платежей не бывает). Проверка дня в отправщике атомарна - не задвоится.
    daily_check_ids = set()
    if company_ids:
        cur.execute(f'''
            SELECT c.id, c.timezone,
                   ARRAY(SELECT nc.period FROM {SCHEMA}.notification_checks nc
                         WHERE nc.company_id = c.id AND nc.kind = 'missing_receipts'
                         ORDER BY nc.checked_at DESC LIMIT 3)
            FROM {SCHEMA}.companies c
            WHERE c.id = ANY(%s)
              AND EXISTS (SELECT 1 FROM {SCHEMA}.user_integrations ui
                          JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
                          JOIN {SCHEMA}.integration_categories ic ON ic.id = p.category_id
                          WHERE ui.company_id = c.id AND ui.status = 'active' AND ic.slug = 'payments')
        ''', (company_ids,))
        for cid, zone, recent_periods in cur.fetchall():
            try:
                zone_info = ZoneInfo(zone or 'Europe/Moscow')
            except Exception:
                zone_info = ZoneInfo('Europe/Moscow')
            yesterday = (datetime.now(zone_info).date() - timedelta(days=1)).isoformat()
            if yesterday not in (recent_periods or []):
                daily_check_ids.add(cid)

    # Поиск пропущенных платежей/чеков - с прошлого успешного поиска (с запасом),
    # после сбоя или незавершённого прохода - за сутки.
    search_from: Dict[int, datetime] = {}
    if receipts_due:
        cur.execute(f'''
            SELECT company_id, finished_at FROM {SCHEMA}.cron_source_runs
            WHERE source = 'ecomkassa_receipts' AND item_key = 'search' AND error IS NULL
              AND company_id = ANY(%s) AND finished_at > NOW() - INTERVAL '1 day'
        ''', (list(receipts_due),))
        search_from = {cid: last - timedelta(minutes=ECOMKASSA_SEARCH_OVERLAP_MIN) for cid, last in cur.fetchall()}
    default_from = datetime.utcnow() - timedelta(hours=ECOMKASSA_AUTO_HOURS)
    search_to = datetime.utcnow() + timedelta(minutes=5)

    tick_id = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    tasks = []
    for company_id in company_ids:
        if company_id in ofd_ids:
            tasks.append((company_id, OFD_URL, {'company_id': company_id}))
        if company_id in ecomkassa_ids:
            # Новые счета/заказы/чеки Екомкассы (и платежи шлюза по ним), если живой хук не пришёл.
            tasks.append((company_id, FETCH_ORDERS_URL, {
                'company_id': company_id, 'auto_hours': ecomkassa_hours,
                'order_types': ['INVC', 'CORD', 'VCHR'], 'statuses': ['PAID', 'COMPLETED'], 'batch_size': 30
            }))
        if source_on(settings, 'automation') and company_id in automation_due:
            tasks.append((company_id, JOBS_URL, {'action': 'run', 'company_id': company_id, 'heartbeat': True}))
        if source_on(settings, 'ecomkassa_receipts') and company_id in receipts_due:
            tasks.append((company_id, RESYNC_URL, {'company_id': company_id}))
            if company_id not in ecomkassa_ids:
                # Страховка от потерянных вебхуков: поиск оплаченных документов за последние часы.
                tasks.append((company_id, FETCH_ORDERS_URL, {
                    'company_id': company_id, 'only_new': True,
                    'date_from': search_from.get(company_id, default_from).isoformat(), 'date_to': search_to.isoformat(),
                    'order_types': ['INVC', 'CORD', 'VCHR'], 'statuses': ['PAID', 'COMPLETED'], 'batch_size': 30,
                    'cron_source': 'ecomkassa_receipts', 'cron_item': 'search'
                }))
    # Очередь автоматизации всех компаний - одним вызовом на каждом шаге, не дожидаясь,
    # пока компания дойдёт в обходе по кругу: повторы и зависшие задания не ждут часами.
    if source_on(settings, 'automation'):
        cur.execute(f'''
            SELECT 1 FROM {SCHEMA}.automation_jobs
            WHERE status IN ('new', 'error') AND next_attempt_at <= NOW()
               OR status = 'processing' AND locked_until < NOW()
            LIMIT 1
        ''')
        if cur.fetchone():
            tasks.append((0, JOBS_URL, {'action': 'run'}))
    for company_id in daily_check_ids:
        tasks.append((company_id, NOTIFICATIONS_URL, {'action': 'dispatch', 'company_id': company_id, 'daily': True}))
    try:
        for company_id in subscription_reminders(cur, conn):
            if company_id not in daily_check_ids:
                tasks.append((company_id, NOTIFICATIONS_URL, {'action': 'dispatch', 'company_id': company_id}))
    except Exception as e:
        conn.rollback()
        print(f'subscription reminders failed: {e}')
    for integration_id, company_id, date_from, date_to in bank_jobs:
        tasks.append((company_id, BANK_URL, {'integration_id': integration_id, 'company_id': company_id,
                                             'date_from': date_from, 'date_to': date_to}))
    # Очередь передачи регистраций в CRM платформы - отдельным вызовом, не задерживая шаг.
    try:
        if platform_crm.load_settings(cur).get('is_enabled') and platform_crm.pending_count(cur):
            tasks.append((0, SELF_URL, {'action': 'crm_process'}))
    except Exception as e:
        conn.rollback()
        print(f'platform crm check failed: {e}')
    # Автопродление подписок по сохранённым картам Т‑Банка (проверка «кому пора» - в самой функции).
    # Источник платформы целиком (company_id = 0 в журнале запусков), частота - из настроек.
    try:
        if source_on(settings, 'subscriptions') and subscriptions_due(cur, settings):
            cur.execute(f'''
                SELECT 1 FROM {SCHEMA}.subscriptions s
                WHERE s.auto_renew = true AND s.card_id IS NOT NULL
                  AND s.current_period_end < NOW() + INTERVAL '1 day'
                  AND s.current_period_end > NOW() - INTERVAL '3 days' LIMIT 1
            ''')
            if cur.fetchone():
                tasks.append((0, SUBSCRIPTION_URL, {'action': 'renew_due'}))
            elif source_interval(settings, 'subscriptions') != 'cron':
                cur.execute(f'''
                    INSERT INTO {SCHEMA}.cron_source_runs (source, company_id, tick, item_key, loaded, error, finished_at)
                    VALUES ('subscriptions', 0, %s, '', 0, NULL, NOW())
                    ON CONFLICT (source, company_id, item_key) DO UPDATE SET
                        tick = EXCLUDED.tick, loaded = 0, error = NULL, finished_at = NOW()
                ''', (str(tick_id)[:40],))
                cur.execute(f'''
                    INSERT INTO {SCHEMA}.cron_run_history (source, company_id, item_key, tick, loaded, error)
                    VALUES ('subscriptions', 0, '', %s, 0, NULL)
                ''', (str(tick_id)[:40],))
                conn.commit()
    except Exception as e:
        conn.rollback()
        print(f'subscription renew check failed: {e}')
    for _, _, task_body in tasks:
        task_body['cron_tick'] = tick_id
    errors: Dict[int, List[str]] = {}
    print(f'[tick] prepared {len(tasks)} tasks in {time.time() - tick_started:.2f}s')
    if tasks:
        # Жёсткий предел на рассылку: отдельный urlopen может висеть дольше своего тайм-аута
        # (соединение + TLS + ответ), а шаг обязан уложиться в тайм-аут функции.
        # Задачи стартуют лесенкой (шаг TASK_STAGGER_SEC), а не все в одну секунду:
        # одновременный старт 8+ функций упирался в лимит запросов к базе
        # («rate limit exceeded») и часть загрузок падала посреди работы.
        pool = ThreadPoolExecutor(max_workers=len(tasks))
        step = min(TASK_STAGGER_SEC, TASK_STAGGER_TOTAL_SEC / len(tasks))

        def staggered(i, url, body):
            time.sleep(i * step)
            return call(url, body, 1.2)

        futures = {pool.submit(staggered, i, t[1], t[2]): t[0] for i, t in enumerate(tasks)}
        done, _ = wait(futures, timeout=1.6 + len(tasks) * step)
        for f in done:
            err = f.result()
            if err:
                errors.setdefault(futures[f], []).append(err)
        pool.shutdown(wait=False)
    print(f'[tick] tasks sent in {time.time() - tick_started:.2f}s')
    summary = {'companies': len(company_ids), 'total_companies': len(all_ids), 'failed': len(errors),
               'started': {'ofd': len(ofd_ids), 'bank': len(bank_jobs), 'ecomkassa': len(ecomkassa_ids),
                           'ecomkassa_receipts': len(receipts_due), 'automation': len(automation_due),
                           'missing_receipts_check': len(daily_check_ids),
                           'ecomkassa_search': [t[0] for t in tasks if t[2].get('cron_item') == 'search']},
               'errors': [{'company_id': k, 'errors': v} for k, v in list(errors.items())[:5]],
               'next_offset': next_offset}
    cur.execute(f'''
        UPDATE {SCHEMA}.platform_settings SET cron_last_tick_at = NOW(), cron_last_result = %s WHERE id = 1
    ''', (json.dumps(summary, ensure_ascii=False),))
    conn.commit()
    try:
        # История запусков нужна только для счётчика за сутки - храним неделю.
        cur.execute(f"DELETE FROM {SCHEMA}.cron_run_history WHERE finished_at < NOW() - INTERVAL '7 days'")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f'cron history cleanup failed: {e}')
    return summary


def cron_payload(cur, settings: Dict[str, Any]) -> Dict[str, Any]:
    """Всё для раздела «Фоновые задачи» админки."""
    return {
        'success': True,
        'cron_enabled': bool(settings['cron_enabled']),
        'cron_token': settings['cron_token'],
        'cron_last_tick_at': settings['cron_last_tick_at'],
        'cron_last_result': settings['cron_last_result'],
        'cron_interval_min': CRON_INTERVAL_MIN,
        'cron_problems': check_cron(settings),
        'cron_sources': cron_sources_view(cur, settings),
        'automation_queue': automation_queue_view(cur),
    }


def run_now(cur, conn, source: str) -> Tuple[int, List[str]]:
    """
    Ручной запуск одной задачи по всем компаниям сразу, без учёта частоты из настроек.
    Итог каждого вызова попадает в журнал как у планировщика (cron_tick) - его видно в списке.
    """
    def companies_with(slugs: List[str]) -> List[int]:
        cur.execute(f'''
            SELECT DISTINCT ui.company_id FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            JOIN {SCHEMA}.companies c ON c.id = ui.company_id
            WHERE p.slug = ANY(%s) AND ui.status = 'active' AND c.status = 'active'
              AND c.id NOT IN ({BLOCKED_COMPANIES_SQL})
            ORDER BY 1
        ''', (slugs,))
        return [r[0] for r in cur.fetchall()]

    tasks: List[Tuple[int, str, Dict[str, Any]]] = []
    if source == 'ofd':
        tasks = [(cid, OFD_URL, {'company_id': cid}) for cid in companies_with(['ofdru'])]
    elif source == 'ecomkassa':
        tasks = [(cid, FETCH_ORDERS_URL, {'company_id': cid, 'auto_hours': ECOMKASSA_AUTO_HOURS,
                                          'order_types': ['INVC', 'CORD', 'VCHR'], 'statuses': ['PAID', 'COMPLETED'],
                                          'batch_size': 30}) for cid in companies_with(['ecomkassa'])]
    elif source == 'ecomkassa_receipts':
        date_from = (datetime.utcnow() - timedelta(hours=ECOMKASSA_AUTO_HOURS)).isoformat()
        date_to = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        for cid in companies_with(['ecomkassa']):
            tasks.append((cid, RESYNC_URL, {'company_id': cid}))
            tasks.append((cid, FETCH_ORDERS_URL, {'company_id': cid, 'only_new': True, 'date_from': date_from,
                                                  'date_to': date_to, 'order_types': ['INVC', 'CORD', 'VCHR'],
                                                  'statuses': ['PAID', 'COMPLETED'], 'batch_size': 30,
                                                  'cron_source': 'ecomkassa_receipts', 'cron_item': 'search'}))
    elif source == 'bank':
        cur.execute(f'''
            SELECT ui.id, ui.company_id,
                   to_char(COALESCE(ui.last_synced_at, NOW() - INTERVAL '3 days') + INTERVAL '3 hours' - INTERVAL '1 day', 'YYYY-MM-DD'),
                   to_char(NOW() + INTERVAL '3 hours', 'YYYY-MM-DD')
            FROM {SCHEMA}.user_integrations ui
            JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
            JOIN {SCHEMA}.companies c ON c.id = ui.company_id
            WHERE p.slug IN ('tbank_account', 'tochka_account') AND ui.status = 'active' AND c.status = 'active'
              AND c.id NOT IN ({BLOCKED_COMPANIES_SQL})
        ''')
        tasks = [(cid, BANK_URL, {'integration_id': iid, 'company_id': cid, 'date_from': d_from, 'date_to': d_to})
                 for iid, cid, d_from, d_to in cur.fetchall()]
    elif source == 'automation':
        cur.execute(f'''
            SELECT c.id FROM {SCHEMA}.companies c
            WHERE c.status = 'active' AND c.id NOT IN ({BLOCKED_COMPANIES_SQL})
              AND (EXISTS (SELECT 1 FROM {SCHEMA}.automation_scenarios s
                           WHERE s.company_id = c.id AND s.status = 'active' AND s.removed_at IS NULL)
                   OR EXISTS (SELECT 1 FROM {SCHEMA}.automation_jobs j
                              WHERE j.company_id = c.id AND j.status IN ('new', 'error', 'processing')))
            ORDER BY 1
        ''')
        tasks = [(r[0], JOBS_URL, {'action': 'run', 'company_id': r[0], 'heartbeat': True}) for r in cur.fetchall()]
        tasks.append((0, JOBS_URL, {'action': 'run'}))
    elif source == 'subscriptions':
        tasks = [(0, SUBSCRIPTION_URL, {'action': 'renew_due'})]
    conn.commit()
    if not tasks:
        return 0, []

    tick_id = 'manual' + datetime.utcnow().strftime('%Y%m%d%H%M%S')
    for _, _, task_body in tasks:
        task_body['cron_tick'] = tick_id
    # Лесенкой, как у планировщика: одновременный старт упирается в лимит запросов к базе.
    step = min(0.4, 2.4 / len(tasks))
    pool = ThreadPoolExecutor(max_workers=len(tasks))

    def staggered(i, url, task_body):
        time.sleep(i * step)
        return call(url, task_body, 1.2)

    futures = {pool.submit(staggered, i, t[1], t[2]): t[0] for i, t in enumerate(tasks)}
    done, _ = wait(futures, timeout=1.6 + len(tasks) * step)
    errors = [f'компания {futures[f]}: {f.result()}' for f in done if f.result()]
    pool.shutdown(wait=False)
    return len(tasks), errors[:5]


def check_cron(settings: Dict[str, Any]) -> List[str]:
    '''Почему автоматический режим может не работать - для сообщения в админке.'''
    problems = []
    if not settings['cron_enabled']:
        return problems
    last = settings['cron_last_tick_at']
    fallback = ' Пока это так, задачи запускаются по-старому - из кабинетов клиентов.'
    if not last:
        problems.append('Планировщик ещё ни разу не вызывал запуск: задание на сервере не настроено. '
                        f'Добавьте его (раз в {CRON_INTERVAL_MIN} мин) по команде ниже.' + fallback)
    elif last < datetime.utcnow() - timedelta(minutes=CRON_STALE_MIN):
        problems.append(f'Планировщик не запускался с {last:%d.%m.%Y %H:%M} UTC - проверьте задание на сервере.' + fallback)
    result = settings.get('cron_last_result') or {}
    if result.get('failed'):
        problems.append(f"При последнем запуске были ошибки у компаний: {result['failed']} из {result.get('companies')}.")
    return problems


def is_platform_owner(cur, user_id) -> bool:
    cur.execute(f'''
        SELECT 1 FROM {SCHEMA}.company_users cu
        JOIN {SCHEMA}.companies c ON c.id = cu.company_id
        WHERE cu.user_id = %s AND cu.status = 'active' AND c.is_platform_admin = true
          AND cu.role_id IN (SELECT id FROM {SCHEMA}.roles WHERE slug = 'owner')
    ''', (user_id,))
    return cur.fetchone() is not None


def platform_members(cur) -> List[Dict[str, Any]]:
    '''Сотрудники компании платформы и их доступ к админке (владелец - всегда).'''
    cur.execute(f'''
        SELECT u.id, u.full_name, u.phone, u.email, r.slug, r.name, cu.platform_admin
        FROM {SCHEMA}.company_users cu
        JOIN {SCHEMA}.companies c ON c.id = cu.company_id AND c.is_platform_admin = true
        JOIN {SCHEMA}.app_users u ON u.id = cu.user_id
        JOIN {SCHEMA}.roles r ON r.id = cu.role_id
        WHERE cu.status = 'active'
        ORDER BY (r.slug = 'owner') DESC, u.full_name NULLS LAST, u.id
    ''')
    return [{'user_id': r[0], 'full_name': r[1], 'phone': r[2], 'email': r[3], 'role_slug': r[4],
             'role_name': r[5], 'is_owner': r[4] == 'owner', 'admin': r[4] == 'owner' or bool(r[6])}
            for r in cur.fetchall()]


# Страницы личного кабинета, где можно показать баннер. 'all' - на всех страницах.
BANNER_PAGES = [
    {'id': 'all', 'name': 'Все страницы'},
    {'id': 'reconciliation', 'name': 'Сверка'},
    {'id': 'events', 'name': 'События'},
    {'id': 'transactions', 'name': 'Транзакции'},
    {'id': 'automation', 'name': 'Автоматизация'},
    {'id': 'integrations', 'name': 'Интеграции'},
    {'id': 'access', 'name': 'Доступ'},
    {'id': 'settings', 'name': 'Настройки'},
]
BANNER_VARIANTS = ('info', 'warning', 'danger', 'success')


def load_banners(cur, only_active: bool = False) -> List[Dict[str, Any]]:
    cur.execute(f'''
        SELECT page, text, button_text, button_url, variant, updated_at, is_active FROM {SCHEMA}.platform_banners
        {"WHERE is_active AND btrim(text) <> ''" if only_active else ''}
    ''')
    return [{'page': r[0], 'text': r[1], 'button_text': r[2], 'button_url': r[3], 'variant': r[4],
             'updated_at': r[5].isoformat() if r[5] else None, 'is_active': bool(r[6])} for r in cur.fetchall()]


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Настройки платформы (только для администраторов платформы) и точка запуска
    фоновых задач по расписанию.
    GET ?requester_user_id= - настройки + список компаний для выбора управляющей
    GET ?public=1 - номер счётчика Яндекс Метрики (без авторизации)
    GET ?banners=1 - баннеры с текстом для страниц кабинета (без авторизации)
    GET ?requester_user_id=&section=banners - все баннеры для редактирования
    POST {action: "save_banner", requester_user_id, page, text, button_text, button_url, variant, is_active}
    POST {action: "save", requester_user_id, managing_company_id, contact_email, contact_phone, contact_address, cron_enabled,
          metrika_counter_id, metrika_script, messenger_api_url} - почта/телефон пусто - владельца управляющей компании, адрес пусто - юр. адрес компании
    POST {action: "save_maintenance", requester_user_id, maintenance_enabled, maintenance_message, maintenance_until}
         - режим техработ: сайт показывает заглушку всем, кроме администраторов платформы
    GET ?requester_user_id=&section=admins - сотрудники компании платформы и доступ к админке
    POST {action: "set_admin", requester_user_id, user_id, enabled} - дать/забрать доступ (только владелец)
    POST {action: "tick"} + заголовок X-Cron-Token - шаг планировщика по всем компаниям
         (работает, только если включён режим cron)
    CRM платформы (Битрикс24, передача регистраций клиентов):
    GET ?requester_user_id=&section=crm - настройки + журнал передачи
    GET ?requester_user_id=&section=crm_reference&webhook_url= - воронки, этапы и поля портала
    POST {action: "save_crm", requester_user_id, webhook_url, is_enabled, entity, stage_id, phone_field, ...}
    POST {action: "crm_retry", requester_user_id, event_id} - повторить передачу события
    POST {action: "crm_process"} - разобрать очередь (внутренний сигнал функций регистрации)
    '''
    denied = guard(event, public_actions=('tick',), public_query=('public', 'banners'), override=('requester_user_id',), check_company=False)
    if denied:
        return denied

    method = event.get('httpMethod', 'GET')
    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    params = event.get('queryStringParameters') or {}
    body = json.loads(event.get('body') or '{}') if method == 'POST' else {}
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}

    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cur = conn.cursor()
    try:
        settings = load_settings(cur)

        if method == 'POST' and body.get('action') == 'tick':
            token = headers.get('x-cron-token') or body.get('token')
            if not token or token != settings['cron_token']:
                return respond(403, {'error': 'Неверный ключ планировщика'})
            if not settings['cron_enabled']:
                return respond(409, {'error': 'Автоматический режим (cron) выключен в настройках платформы'})
            return respond(200, {'success': True, **tick(cur, conn, settings)})

        if method == 'POST' and body.get('action') == 'crm_process':
            # Сигнал от регистрации/профиля/компании (подписан ключом сервиса - пропущен guard).
            if headers.get('x-service-sign'):
                return respond(200, {'success': True, **platform_crm.process_queue(cur, conn, 0.8, max_events=1)})

        # Публично: баннеры для страниц личного кабинета (пустой текст - баннера нет).
        if method == 'GET' and params.get('banners') == '1':
            return respond(200, {'success': True, 'banners': load_banners(cur, only_active=True)})

        # Публично: номер счётчика Метрики и реквизиты управляющей компании (оператор в документах сайта).
        if method == 'GET' and params.get('public') == '1':
            operator = None
            if settings.get('managing_company_id'):
                cur.execute(f'''
                    SELECT COALESCE(NULLIF(full_name, ''), name), inn, ogrn, legal_address
                    FROM {SCHEMA}.companies WHERE id = %s
                ''', (settings['managing_company_id'],))
                row = cur.fetchone()
                if row:
                    operator = {'name': row[0], 'inn': row[1], 'ogrn': row[2],
                                'address': settings.get('contact_address') or row[3],
                                'email': settings.get('contact_email') or settings.get('contact_email_default'),
                                'phone': settings.get('contact_phone') or settings.get('contact_phone_default')}
            return respond(200, {'success': True, 'metrika_counter_id': settings.get('metrika_counter_id'),
                                 'metrika_script': settings.get('metrika_script'),
                                 'operator': operator, 'maintenance': {
                                     'enabled': settings['maintenance_enabled'],
                                     'message': settings['maintenance_message'],
                                     'until': settings['maintenance_until'],
                                 }})

        requester = body.get('requester_user_id') or params.get('requester_user_id')
        if not requester or not is_admin(cur, requester):
            return respond(403, {'error': 'Доступно только администраторам платформы'})

        if method == 'GET' and params.get('section') == 'banners':
            return respond(200, {'success': True, 'banners': load_banners(cur), 'pages': BANNER_PAGES})

        if method == 'POST' and body.get('action') == 'save_banner':
            page = body.get('page')
            if page not in {p['id'] for p in BANNER_PAGES}:
                return respond(400, {'error': 'Неизвестная страница'})
            variant = body.get('variant') if body.get('variant') in BANNER_VARIANTS else 'info'
            url = str(body.get('button_url') or '').strip()[:500]
            if url and not re.match(r'^(https?://|/)', url):
                return respond(400, {'error': 'Ссылка должна начинаться с https:// или /'})
            cur.execute(f'''
                INSERT INTO {SCHEMA}.platform_banners (page, text, button_text, button_url, variant, is_active, updated_by, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (page) DO UPDATE SET text = EXCLUDED.text, button_text = EXCLUDED.button_text,
                    button_url = EXCLUDED.button_url, variant = EXCLUDED.variant, is_active = EXCLUDED.is_active,
                    updated_by = EXCLUDED.updated_by, updated_at = NOW()
            ''', (page, str(body.get('text') or '').strip()[:2000], str(body.get('button_text') or '').strip()[:80],
                  url, variant, body.get('is_active') is not False, requester))
            conn.commit()
            return respond(200, {'success': True, 'banners': load_banners(cur), 'pages': BANNER_PAGES})

        if method == 'GET' and params.get('section') == 'crm':
            return respond(200, {'success': True, 'crm': platform_crm.load_settings(cur),
                                 'events': platform_crm.recent_events(cur),
                                 'pending': platform_crm.pending_count(cur)})

        if method == 'GET' and params.get('section') == 'crm_reference':
            url = str(params.get('webhook_url') or '').strip() or (platform_crm.load_settings(cur).get('webhook_url') or '')
            if url and not url.endswith('/'):
                url += '/'
            err = platform_crm.valid_webhook(url)
            if err:
                return respond(200, {'success': False, 'error': err})
            ref, err = platform_crm.load_reference(url)
            if err:
                return respond(200, {'success': False, 'error': err})
            return respond(200, {'success': True, **ref})

        if method == 'POST' and body.get('action') == 'save_crm':
            err = platform_crm.save_settings(cur, int(requester), body)
            if err:
                conn.rollback()
                return respond(400, {'error': err})
            conn.commit()
            stats = platform_crm.process_queue(cur, conn, 0.5, max_events=1)
            return respond(200, {'success': True, 'crm': platform_crm.load_settings(cur), 'processed': stats,
                                 'events': platform_crm.recent_events(cur), 'pending': platform_crm.pending_count(cur)})

        if method == 'POST' and body.get('action') == 'crm_retry':
            crm_settings = platform_crm.load_settings(cur)
            if not crm_settings.get('is_enabled') or not crm_settings.get('webhook_url'):
                return respond(400, {'error': 'Передача в CRM выключена — включите её и сохраните настройки'})
            if body.get('event_id'):
                platform_crm.retry_event(cur, int(body['event_id']))
                conn.commit()
            # По кнопке - одно событие за запрос: передача клиента с компанией занимает до ~2 с,
            # иначе запрос не укладывается в тайм-аут функции. Очередь до конца гоняет кабинет.
            stats = platform_crm.process_queue(cur, conn, 1.0, max_events=1)
            return respond(200, {'success': True, 'processed': stats, 'events': platform_crm.recent_events(cur),
                                 'pending': platform_crm.pending_count(cur)})

        if method == 'GET' and params.get('section') == 'admins':
            return respond(200, {'success': True, 'members': platform_members(cur),
                                 'can_manage': is_platform_owner(cur, requester)})

        if method == 'POST' and body.get('action') == 'set_admin':
            if not is_platform_owner(cur, requester):
                return respond(403, {'error': 'Назначать администраторов может только владелец компании платформы'})
            cur.execute(f'''
                UPDATE {SCHEMA}.company_users cu SET platform_admin = %s, updated_at = NOW()
                FROM {SCHEMA}.companies c
                WHERE cu.company_id = c.id AND c.is_platform_admin = true
                  AND cu.user_id = %s AND cu.status = 'active'
                  AND cu.role_id NOT IN (SELECT id FROM {SCHEMA}.roles WHERE slug = 'owner')
                RETURNING cu.id
            ''', (bool(body.get('enabled')), body.get('user_id')))
            if not cur.fetchone():
                conn.rollback()
                return respond(404, {'error': 'Сотрудник не найден в компании платформы'})
            conn.commit()
            return respond(200, {'success': True, 'members': platform_members(cur), 'can_manage': True})

        if method == 'POST' and body.get('action') == 'save_messenger':
            messenger = str(body.get('messenger_api_url') or '').strip().rstrip('/')[:500] or None
            if messenger and not re.match(r'^https://[^\s/]+\.[^\s]+$', messenger):
                return respond(400, {'error': 'Адрес отправки должен начинаться с https://'})
            cur.execute(f'''
                UPDATE {SCHEMA}.platform_settings SET messenger_api_url = %s, updated_by = %s, updated_at = NOW() WHERE id = 1
            ''', (messenger, requester))
            conn.commit()
            return respond(200, {'success': True, 'messenger_api_url': messenger})

        if method == 'POST' and body.get('action') == 'save_cron':
            keys = {src['key'] for src in CRON_SOURCES}
            sources = {k: bool(v) for k, v in (body.get('cron_sources') or {}).items() if k in keys}
            intervals = {k: v for k, v in (body.get('cron_intervals') or {}).items() if k in keys and v in INTERVAL_PRESETS}
            cur.execute(f'''
                UPDATE {SCHEMA}.platform_settings
                SET cron_enabled = %s, cron_sources = %s, cron_intervals = %s, updated_by = %s, updated_at = NOW()
                WHERE id = 1
            ''', (bool(body.get('cron_enabled')), json.dumps(sources), json.dumps(intervals), requester))
            conn.commit()
            settings = load_settings(cur)
            return respond(200, cron_payload(cur, settings))

        if method == 'POST' and body.get('action') == 'run_now':
            source = body.get('source')
            if source not in {src['key'] for src in CRON_SOURCES}:
                return respond(400, {'error': 'Неизвестная задача'})
            started, errors = run_now(cur, conn, source)
            settings = load_settings(cur)
            return respond(200, {**cron_payload(cur, settings), 'started': started, 'errors': errors})

        if method == 'GET' and params.get('section') == 'cron':
            return respond(200, cron_payload(cur, settings))

        if method == 'POST' and body.get('action') == 'save_maintenance':
            until = str(body.get('maintenance_until') or '').strip() or None
            cur.execute(f'''
                UPDATE {SCHEMA}.platform_settings
                SET maintenance_enabled = %s, maintenance_message = %s, maintenance_until = %s::timestamptz,
                    updated_by = %s, updated_at = NOW()
                WHERE id = 1
            ''', (bool(body.get('maintenance_enabled')), str(body.get('maintenance_message') or '').strip()[:500] or None,
                  until, requester))
            conn.commit()
            settings = load_settings(cur)

        elif method == 'POST':
            if body.get('action') != 'save':
                return respond(400, {'error': 'Unknown action'})
            company_id = body.get('managing_company_id')
            if company_id:
                cur.execute(f'SELECT 1 FROM {SCHEMA}.companies WHERE id = %s', (company_id,))
                if not cur.fetchone():
                    return respond(400, {'error': 'Компания не найдена'})
            metrika = re.sub(r'\D', '', str(body.get('metrika_counter_id') or ''))[:20] or None
            metrika_script = (str(body['metrika_script'] or '').strip()[:20000] or None) if 'metrika_script' in body else settings.get('metrika_script')
            if metrika_script:
                found = re.search(r'ym\(\s*(\d+)\s*,\s*[\'"]init', metrika_script)
                if not found or 'mc.yandex.ru/metrika/tag.js' not in metrika_script:
                    return respond(400, {'error': 'Это не похоже на код счётчика Яндекс Метрики: вставьте код целиком из настроек счётчика'})
                metrika = found.group(1)
            messenger = (str(body['messenger_api_url'] or '').strip().rstrip('/')[:500] or None) if 'messenger_api_url' in body else settings.get('messenger_api_url')
            if messenger and not re.match(r'^https://[^\s/]+\.[^\s]+$', messenger):
                return respond(400, {'error': 'Адрес отправки должен начинаться с https://'})
            keys = {src['key'] for src in CRON_SOURCES}
            sources = {k: bool(v) for k, v in (body['cron_sources'] if isinstance(body.get('cron_sources'), dict) else settings.get('cron_sources') or {}).items() if k in keys}
            intervals = {k: v for k, v in (body['cron_intervals'] if isinstance(body.get('cron_intervals'), dict) else settings.get('cron_intervals') or {}).items()
                         if k in keys and v in INTERVAL_PRESETS}
            email = (str(body['contact_email'] or '').strip()[:255] or None) if 'contact_email' in body else settings.get('contact_email')
            if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                return respond(400, {'error': 'Проверьте адрес почты'})
            phone = (str(body['contact_phone'] or '').strip()[:50] or None) if 'contact_phone' in body else settings.get('contact_phone')
            if phone and len(re.sub(r'\D', '', phone)) < 10:
                return respond(400, {'error': 'Проверьте номер телефона'})
            address = (str(body['contact_address'] or '').strip()[:500] or None) if 'contact_address' in body else settings.get('contact_address')
            cur.execute(f'''
                UPDATE {SCHEMA}.platform_settings
                SET contact_address = %s, contact_email = %s, contact_phone = %s, managing_company_id = %s, cron_enabled = %s, metrika_counter_id = %s, metrika_script = %s, cron_sources = %s, cron_intervals = %s,
                    messenger_api_url = %s, updated_by = %s, updated_at = NOW()
                WHERE id = 1
            ''', (address, email, phone, company_id or None, (bool(body['cron_enabled']) if 'cron_enabled' in body else bool(settings['cron_enabled'])), metrika, metrika_script, json.dumps(sources), json.dumps(intervals), messenger, requester))
            conn.commit()
            settings = load_settings(cur)

        cur.execute(f'''
            SELECT id, name, inn FROM {SCHEMA}.companies WHERE status = 'active' ORDER BY name
        ''')
        companies = [{'id': r[0], 'name': r[1], 'inn': r[2]} for r in cur.fetchall()]
        return respond(200, {
            'success': True,
            'settings': settings,
            'companies': companies,
            'cron_interval_min': CRON_INTERVAL_MIN,
            'cron_problems': check_cron(settings),
            'cron_sources': cron_sources_view(cur, settings),
            'automation_queue': automation_queue_view(cur)
        })
    finally:
        cur.close()
        conn.close()
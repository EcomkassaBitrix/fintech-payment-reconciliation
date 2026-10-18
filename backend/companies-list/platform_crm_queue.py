'''
Очередь передачи в CRM платформы (Битрикс24): событие пишется в platform_crm_events,
platform-settings разбирает очередь по сигналу (без ожидания), по шагу планировщика и из админки.
Сбой постановки не ломает регистрацию, профиль и создание компании.
Одинаковая копия - в auth-phone, profile-update и companies-list.
'''
import json
import threading
import urllib.request
from typing import Any, Dict, Optional

from auth_guard import internal_headers

SCHEMA = 't_p83864310_fintech_payment_reco'
PLATFORM_SETTINGS_URL = 'https://functions.poehali.dev/9e410f34-57f5-40ff-85f6-ccc802b812d9'


def enqueue(cur, kind: str, user_id: Optional[int] = None, company_id: Optional[int] = None,
            payload: Optional[Dict[str, Any]] = None) -> bool:
    '''Ставит событие, только если передача в CRM включена. Returns: поставлено ли.'''
    try:
        cur.execute(f'SELECT is_enabled FROM {SCHEMA}.platform_crm_settings WHERE id = 1')
        row = cur.fetchone()
        if not row or not row[0]:
            return False
        if kind == 'profile':
            # Несколько сохранений профиля подряд - одно событие: берём актуальные данные при отправке.
            cur.execute(f'''
                SELECT 1 FROM {SCHEMA}.platform_crm_events
                WHERE kind = 'profile' AND user_id = %s AND status IN ('new', 'retry') LIMIT 1
            ''', (user_id,))
            if cur.fetchone():
                return True
        cur.execute(f'''
            INSERT INTO {SCHEMA}.platform_crm_events (kind, user_id, company_id, payload)
            VALUES (%s, %s, %s, %s)
        ''', (kind, user_id, company_id, json.dumps(payload or {}, ensure_ascii=False)))
        return True
    except Exception as e:
        print(f'[platform_crm] enqueue {kind} failed: {e}')
        return False


def _post() -> None:
    try:
        req = urllib.request.Request(
            PLATFORM_SETTINGS_URL, data=json.dumps({'action': 'crm_process'}).encode('utf-8'),
            headers={'Content-Type': 'application/json', **internal_headers()}, method='POST')
        urllib.request.urlopen(req, timeout=1.5).close()
    except Exception:
        pass


def signal() -> None:
    '''Будит разбор очереди, не дожидаясь результата (потерянный сигнал подберёт планировщик).'''
    t = threading.Thread(target=_post, daemon=True)
    t.start()
    t.join(timeout=1.6)

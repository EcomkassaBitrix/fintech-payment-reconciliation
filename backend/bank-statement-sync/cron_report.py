import json
import os
import time
from typing import Any, Dict

import psycopg2

SCHEMA = 't_p83864310_fintech_payment_reco'


def record_cron_run(event: Dict[str, Any], resp: Dict[str, Any], source: str, loaded_key: str) -> None:
    '''
    Итог вызова, запущенного планировщиком (в теле есть cron_tick): сколько загружено
    и была ли ошибка - для блока «Фоновые задачи» в админке. Ручные вызовы не пишутся.
    '''
    try:
        req = json.loads(event.get('body') or '{}')
    except (TypeError, ValueError):
        return
    tick = req.get('cron_tick')
    company_id = req.get('company_id')
    if not tick or not company_id:
        return
    try:
        out = json.loads(resp.get('body') or '{}')
    except (TypeError, ValueError):
        out = {}
    failed = resp.get('statusCode', 200) >= 400 or out.get('success') is False
    if out.get('pending'):
        failed = False
    error = (str(out.get('error') or 'Ошибка')[:300]) if failed else None
    if out.get('pending'):
        error = 'pending'
    value = out.get(loaded_key) or 0
    if isinstance(value, dict):
        value = sum(v for v in value.values() if isinstance(v, int))
    loaded = 0 if failed else int(value)
    for attempt in range(3):
        try:
            conn = psycopg2.connect(os.environ['DATABASE_URL'])
            try:
                cur = conn.cursor()
                cur.execute(f'''
                    INSERT INTO {SCHEMA}.cron_source_runs (source, company_id, tick, item_key, loaded, error, finished_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (source, company_id, item_key) DO UPDATE SET
                        tick = EXCLUDED.tick, loaded = EXCLUDED.loaded, error = EXCLUDED.error, finished_at = NOW()
                ''', (source, int(company_id), str(tick)[:40], str(req.get('integration_id') or ''), loaded, error))
                conn.commit()
            finally:
                conn.close()
            return
        except psycopg2.Error as e:
            if attempt == 2 or 'rate limit' not in str(e):
                print(f'[cron_report] {e}')
                return
            time.sleep(0.7 * (attempt + 1))

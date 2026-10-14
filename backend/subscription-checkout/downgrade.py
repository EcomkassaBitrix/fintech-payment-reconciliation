'''
Переход на тариф с меньшими лимитами: что не помещается в новый тариф и безвозвратное
удаление того, что клиент не оставил (компании, пользователи, интеграции, сценарии).
'''
from typing import Any, Dict, List, Optional

SCHEMA = 't_p83864310_fintech_payment_reco'


def _ids(cur, sql: str, params) -> List[int]:
    cur.execute(sql, params)
    return [r[0] for r in cur.fetchall()]


def company_owner(cur, company_id) -> Optional[int]:
    cur.execute(f'''
        SELECT cu.user_id FROM {SCHEMA}.company_users cu JOIN {SCHEMA}.roles r ON r.id = cu.role_id
        WHERE cu.company_id = %s AND cu.status = 'active' AND r.slug = 'owner'
        ORDER BY cu.created_at LIMIT 1
    ''', (company_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _section(limit, items):
    over = limit is not None and len(items) > limit
    return {'limit': limit, 'count': len(items), 'items': items} if over else None


def _companies(cur, company_id, tariff) -> Optional[Dict[str, Any]]:
    owner = company_owner(cur, company_id)
    if not owner:
        return None
    cur.execute(f'''
        SELECT c.id, c.name, c.is_platform_admin, t.id IS NOT NULL, t.max_companies
        FROM {SCHEMA}.company_users cu
        JOIN {SCHEMA}.roles r ON r.id = cu.role_id AND r.slug = 'owner'
        JOIN {SCHEMA}.companies c ON c.id = cu.company_id
        LEFT JOIN {SCHEMA}.subscriptions s ON s.company_id = c.id
        LEFT JOIN {SCHEMA}.tariffs t ON t.id = s.tariff_id
        WHERE cu.user_id = %s AND cu.status = 'active'
        ORDER BY c.created_at, c.id
    ''', (owner,))
    rows = cur.fetchall()
    # Лимит компаний считается по лучшему тарифу владельца (как при создании компании).
    others = [r[4] for r in rows if r[0] != int(company_id) and r[3]]
    current = [r[4] for r in rows if r[0] == int(company_id) and r[3]]

    def best(values):
        return None if any(x is None for x in values) else max(values)

    limit = best(others + [tariff['max_companies']])
    old_limit = best(others + current) if current else limit
    # Удаляем компании, только если именно этот переход уменьшает лимит.
    if limit is None or (old_limit is not None and limit >= old_limit):
        return None
    items = [{
        'id': r[0], 'name': r[1],
        'locked': r[0] == int(company_id) or bool(r[2]),
        'note': 'Текущая компания' if r[0] == int(company_id) else ('Компания платформы' if r[2] else None)
    } for r in rows]
    return _section(limit, items)


def _users(cur, company_id, tariff, payer_id) -> Optional[Dict[str, Any]]:
    cur.execute(f'''
        SELECT cu.user_id, COALESCE(NULLIF(u.full_name, ''), u.phone), r.name, r.slug, cu.status
        FROM {SCHEMA}.company_users cu
        JOIN {SCHEMA}.app_users u ON u.id = cu.user_id
        JOIN {SCHEMA}.roles r ON r.id = cu.role_id
        WHERE cu.company_id = %s AND cu.status IN ('active', 'pending')
        ORDER BY cu.created_at, cu.id
    ''', (company_id,))
    items = [{
        'id': f'u:{r[0]}', 'name': r[1], 'note': r[2] if r[4] == 'active' else f'{r[2]}, ожидает входа',
        'locked': r[3] == 'owner' or r[0] == payer_id
    } for r in cur.fetchall()]
    cur.execute(f'''
        SELECT i.id, COALESCE(NULLIF(i.full_name, ''), i.phone), r.name
        FROM {SCHEMA}.invite_tokens i JOIN {SCHEMA}.roles r ON r.id = i.role_id
        WHERE i.company_id = %s AND i.status = 'pending' AND i.expires_at > NOW()
        ORDER BY i.created_at
    ''', (company_id,))
    items += [{'id': f'i:{r[0]}', 'name': r[1], 'note': f'{r[2]}, приглашение', 'locked': False}
              for r in cur.fetchall()]
    return _section(tariff['max_users'], items)


def _integrations(cur, company_id, tariff) -> Optional[Dict[str, Any]]:
    cur.execute(f'''
        SELECT ui.id, COALESCE(NULLIF(ui.integration_name, ''), p.name), p.name
        FROM {SCHEMA}.user_integrations ui
        LEFT JOIN {SCHEMA}.integration_providers p ON p.id = ui.provider_id
        WHERE ui.company_id = %s AND ui.status NOT IN ('deleted', 'hidden')
        ORDER BY ui.created_at, ui.id
    ''', (company_id,))
    items = [{'id': r[0], 'name': r[1], 'note': r[2], 'locked': False} for r in cur.fetchall()]
    return _section(tariff['max_integrations'], items)


def _automations(cur, company_id, tariff) -> Optional[Dict[str, Any]]:
    limit = tariff['max_automations']
    if 'automation' not in (tariff['modules'] or []):
        limit = 0
    cur.execute(f'''
        SELECT id, name FROM {SCHEMA}.automation_scenarios
        WHERE company_id = %s AND removed_at IS NULL ORDER BY created_at, id
    ''', (company_id,))
    items = [{'id': r[0], 'name': r[1], 'note': None, 'locked': False} for r in cur.fetchall()]
    return _section(limit, items)


def overage(cur, company_id, tariff, payer_id) -> Dict[str, Any]:
    '''Что не помещается в лимиты тарифа. Пустой словарь - всё помещается.'''
    result = {
        'companies': _companies(cur, company_id, tariff),
        'users': _users(cur, company_id, tariff, payer_id),
        'integrations': _integrations(cur, company_id, tariff),
        'automations': _automations(cur, company_id, tariff),
    }
    return {k: v for k, v in result.items() if v}


def check_keep(over: Dict[str, Any], keep: Dict[str, Any]) -> Optional[str]:
    '''Проверка выбора клиента: обязательные оставлены, лимит не превышен.'''
    labels = {'companies': 'компаний', 'users': 'пользователей',
              'integrations': 'интеграций', 'automations': 'сценариев'}
    for key, sec in over.items():
        chosen = {str(x) for x in (keep.get(key) or [])}
        valid = {str(i['id']) for i in sec['items']}
        locked = {str(i['id']) for i in sec['items'] if i['locked']}
        chosen &= valid
        if not locked <= chosen:
            return 'Обязательные элементы нельзя удалить'
        if len(chosen) > sec['limit']:
            return f'Выберите не больше {sec["limit"]} {labels[key]}'
    return None


def to_delete(over: Dict[str, Any], keep: Dict[str, Any]) -> Dict[str, list]:
    result = {}
    for key, sec in over.items():
        chosen = {str(x) for x in (keep.get(key) or [])}
        result[key] = [i['id'] for i in sec['items'] if str(i['id']) not in chosen and not i['locked']]
    return result


def delete_scenarios(cur, ids: List[int]) -> None:
    '''Сценарии сверх тарифа не стираются, а скрываются: клиент их не видит, админ платформы может вернуть.'''
    if not ids:
        return
    cur.execute(f'''
        UPDATE {SCHEMA}.automation_scenarios
        SET hidden_prev_status = status, hidden_at = NOW(), removed_at = NOW(), status = 'stopped', updated_at = NOW()
        WHERE id = ANY(%s) AND removed_at IS NULL
    ''', (ids,))


def delete_integrations(cur, ids: List[int]) -> None:
    '''Интеграции сверх тарифа скрываются вместе с их сценариями. Данные и история не трогаются.'''
    if not ids:
        return
    delete_scenarios(cur, _ids(cur, f'''
        SELECT id FROM {SCHEMA}.automation_scenarios
        WHERE (source_integration_id = ANY(%s) OR target_integration_id = ANY(%s)) AND removed_at IS NULL
    ''', (ids, ids)))
    cur.execute(f'''
        UPDATE {SCHEMA}.user_integrations
        SET hidden_prev_status = status, hidden_at = NOW(), status = 'hidden', updated_at = NOW()
        WHERE id = ANY(%s) AND status NOT IN ('deleted', 'hidden')
    ''', (ids,))


def delete_users(cur, company_id, keys: List[str]) -> None:
    user_ids = [int(k[2:]) for k in keys if k.startswith('u:')]
    invite_ids = [int(k[2:]) for k in keys if k.startswith('i:')]
    if user_ids:
        cur.execute(f'DELETE FROM {SCHEMA}.notification_preferences WHERE company_id = %s AND user_id = ANY(%s)',
                    (company_id, user_ids))
        cur.execute(f'DELETE FROM {SCHEMA}.company_users WHERE company_id = %s AND user_id = ANY(%s)',
                    (company_id, user_ids))
    if invite_ids:
        cur.execute(f'DELETE FROM {SCHEMA}.invite_tokens WHERE company_id = %s AND id = ANY(%s)',
                    (company_id, invite_ids))


def delete_company(cur, company_id: int) -> None:
    delete_scenarios(cur, _ids(cur, f'SELECT id FROM {SCHEMA}.automation_scenarios WHERE company_id = %s',
                               (company_id,)))
    delete_integrations(cur, _ids(cur, f'SELECT id FROM {SCHEMA}.user_integrations WHERE company_id = %s',
                                  (company_id,)))
    cur.execute(f'''DELETE FROM {SCHEMA}.automation_job_log WHERE job_id IN
                    (SELECT id FROM {SCHEMA}.automation_jobs WHERE company_id = %s)''', (company_id,))
    cur.execute(f'''DELETE FROM {SCHEMA}.webhook_forward_logs WHERE webhook_payment_id IN
                    (SELECT id FROM {SCHEMA}.webhook_payments WHERE company_id = %s)''', (company_id,))
    cur.execute(f'''DELETE FROM {SCHEMA}.notification_deliveries WHERE notification_id IN
                    (SELECT id FROM {SCHEMA}.notifications WHERE company_id = %s)''', (company_id,))
    cur.execute(f'''DELETE FROM {SCHEMA}.notification_reads WHERE notification_id IN
                    (SELECT id FROM {SCHEMA}.notifications WHERE company_id = %s)''', (company_id,))
    for table in ('automation_documents', 'automation_jobs', 'webhook_payments', 'webhook_events',
                  'payment_carts', 'ecomkassa_receipts', 'crm_deals', 'bank_statement_transactions',
                  'ofd_receipts', 'manual_transaction_links', 'transaction_link_exclusions',
                  'reconciliation_snapshots', 'notifications', 'notification_checks',
                  'notification_preferences', 'cron_source_runs', 'company_bank_oauth_grants',
                  'invite_tokens', 'company_users', 'subscription_payments', 'subscriptions'):
        cur.execute(f'DELETE FROM {SCHEMA}.{table} WHERE company_id = %s', (company_id,))
    cur.execute(f'DELETE FROM {SCHEMA}.companies WHERE id = %s', (company_id,))


def apply(cur, company_id, removal: Dict[str, list]) -> Dict[str, int]:
    delete_scenarios(cur, [int(x) for x in removal.get('automations', [])])
    delete_integrations(cur, [int(x) for x in removal.get('integrations', [])])
    delete_users(cur, company_id, [str(x) for x in removal.get('users', [])])
    for cid in removal.get('companies', []):
        delete_company(cur, int(cid))
    return {k: len(v) for k, v in removal.items()}
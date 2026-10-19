import json
import os
import psycopg2
from typing import Dict, Any
from auth_guard import guard


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Получение списка компаний, доступных пользователю, с его ролью в каждой
    Args: user_id (query параметр)
    Returns: список компаний с ролью пользователя и статусом подписки
    '''
    denied = guard(event)
    if denied:
        return denied


    method = event.get('httpMethod', 'GET')

    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Max-Age': '86400'
            },
            'body': '',
            'isBase64Encoded': False
        }

    if method != 'GET':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    params = event.get('queryStringParameters', {}) or {}
    user_id = params.get('user_id')

    if not user_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'user_id required'}),
            'isBase64Encoded': False
        }

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT
                c.id, c.name, c.inn, c.status,
                r.slug, r.name, r.color,
                s.status, s.trial_ends_at, s.current_period_end,
                t.name, t.max_users, c.timezone, r.modules,
                t.modules, t.max_integrations, t.max_automations, c.is_platform_admin, cu.platform_admin, t.slug,
                (NOT c.is_platform_admin AND (s.id IS NULL OR s.status NOT IN ('trial', 'active')
                 OR COALESCE(CASE WHEN s.status = 'trial' THEN s.trial_ends_at ELSE s.current_period_end END, 'infinity') < NOW()))
            FROM company_users cu
            JOIN companies c ON c.id = cu.company_id
            JOIN roles r ON r.id = cu.role_id
            LEFT JOIN subscriptions s ON s.company_id = c.id
            LEFT JOIN tariffs t ON t.id = s.tariff_id
            WHERE cu.user_id = %s AND cu.status = 'active'
            ORDER BY c.name
        ''', (user_id,))

        companies = []
        for row in cur.fetchall():
            companies.append({
                'id': row[0],
                'name': row[1],
                'inn': row[2],
                'status': row[3],
                'role_slug': row[4],
                'role_name': row[5],
                'role_color': row[6],
                'subscription_status': row[7],
                'trial_ends_at': row[8].isoformat() if row[8] else None,
                'current_period_end': row[9].isoformat() if row[9] else None,
                'tariff_name': row[10],
                'tariff_slug': row[19],
                'max_users': row[11],
                'timezone': row[12] or 'Europe/Moscow',
                'role_modules': row[13] or [],
                # Нет подписки/тарифа - ограничений тарифа нет (None).
                'tariff_modules': row[14],
                'max_integrations': row[15],
                'max_automations': row[16],
                # Админка платформы - владельцу компании-администратора платформы и отмеченным им сотрудникам.
                'platform_admin': bool(row[17]) and (row[4] == 'owner' or bool(row[18])),
                'subscription_blocked': bool(row[20])
            })

        # Компании, открывшие доступ поддержке: админ платформы работает в них с правами админа компании.
        if any(c['platform_admin'] for c in companies):
            own_ids = [c['id'] for c in companies]
            cur.execute('''
                SELECT
                    c.id, c.name, c.inn, c.status,
                    s.status, s.trial_ends_at, s.current_period_end,
                    t.name, t.max_users, c.timezone, r.modules,
                    t.modules, t.max_integrations, t.max_automations, t.slug, c.support_access_until,
                    (NOT c.is_platform_admin AND (s.id IS NULL OR s.status NOT IN ('trial', 'active')
                 OR COALESCE(CASE WHEN s.status = 'trial' THEN s.trial_ends_at ELSE s.current_period_end END, 'infinity') < NOW()))
                FROM companies c
                JOIN roles r ON r.slug = 'admin'
                LEFT JOIN subscriptions s ON s.company_id = c.id
                LEFT JOIN tariffs t ON t.id = s.tariff_id
                WHERE c.support_access_enabled
                  AND (c.support_access_until IS NULL OR c.support_access_until > NOW())
                  AND NOT (c.id = ANY(%s))
                ORDER BY c.name
            ''', (own_ids,))
            for row in cur.fetchall():
                companies.append({
                    'id': row[0],
                    'name': row[1],
                    'inn': row[2],
                    'status': row[3],
                    'role_slug': 'admin',
                    'role_name': 'Поддержка',
                    'role_color': 'bg-info',
                    'subscription_status': row[4],
                    'trial_ends_at': row[5].isoformat() if row[5] else None,
                    'current_period_end': row[6].isoformat() if row[6] else None,
                    'tariff_name': row[7],
                    'tariff_slug': row[14],
                    'max_users': row[8],
                    'timezone': row[9] or 'Europe/Moscow',
                    'role_modules': row[10] or [],
                    'tariff_modules': row[11],
                    'max_integrations': row[12],
                    'max_automations': row[13],
                    'platform_admin': False,
                    'support_access': True,
                    'subscription_blocked': bool(row[16]),
                    'support_access_until': row[15].isoformat() if row[15] else None
                })

        # Режим фоновых задач платформы: при включённом cron кабинет их сам не запускает.
        # Страховка: если планировщик не запускался последние 5 минут (не настроен или
        # упал), кабинеты продолжают запускать задачи сами - работа клиентов не встаёт.
        cur.execute('''
            SELECT cron_enabled AND cron_last_tick_at > NOW() - INTERVAL '5 minutes'
            FROM t_p83864310_fintech_payment_reco.platform_settings WHERE id = 1
        ''')
        row = cur.fetchone()
        cron_enabled = bool(row and row[0])

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'companies': companies,
                'cron_enabled': cron_enabled
            }),
            'isBase64Encoded': False
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)}),
            'isBase64Encoded': False
        }
    finally:
        cur.close()
        conn.close()
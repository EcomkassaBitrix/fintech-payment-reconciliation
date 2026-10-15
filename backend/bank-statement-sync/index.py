import json
import os
import re
import time
import psycopg2
import psycopg2.extras
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from tbank_oauth import fetch_statement as fetch_tbank_statement
from purpose_classifier import matches_keywords, get_purpose_keywords, operation_purpose_text
import tochka_oauth
from ru_trusted_ca import build_ssl_context
from acquiring_settlement import process_acquiring_settlements
from cron_report import record_cron_run
from auth_guard import guard

# enter.tochka.com отдаёт TLS-сертификат, подписанный НУЦ Минцифры РФ (ГОСТ) -
# системное доверенное хранилище Python его не знает без этого контекста.
TOCHKA_SSL_CONTEXT = build_ssl_context()

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400'
}


def normalize_tx(external_id, operation_date, amount, direction, counterparty_name,
                  counterparty_inn, purpose, raw) -> Dict[str, Any]:
    return {
        'external_id': external_id,
        'operation_date': operation_date,
        'amount': amount,
        'direction': direction,
        'counterparty_name': counterparty_name,
        'counterparty_inn': counterparty_inn,
        'purpose': purpose,
        'raw': raw
    }


def get_tbank_access(cur, company_id: int) -> Dict[str, Any]:
    '''
    Достаёт токен доступа T-Business ID для компании, если владелец уже подтвердил
    токен Т-Бизнес. Если токена нет - пустой словарь, выписку не грузим.
    '''
    cur.execute('''
        SELECT access_token
        FROM t_p83864310_fintech_payment_reco.company_bank_oauth_grants
        WHERE company_id = %s AND provider_slug = 'tbank_account' AND NOT is_sandbox
    ''', (company_id,))
    row = cur.fetchone()

    if row and row[0]:
        return {'access_token': row[0]}

    return {}


def fetch_tbank_account_statement(cur, integration_id: int, company_id: int, config: Dict[str, Any],
                                   date_from: str, date_to: str) -> Optional[List[Dict[str, Any]]]:
    '''
    Расчётный счёт Т-Банка (T-Business ID + T-API, https://developer.tbank.ru/docs/products/account-info).
    Используем токен Т-Бизнес компании. Каждая операция фильтруется по
    ключевым словам из настройки интеграции (purpose_keywords) - в БД попадает
    операция, только если её назначение платежа содержит хотя бы одно из слов.
    Если ключевые слова не заданы - загружаются все операции без фильтрации.
    '''
    access = get_tbank_access(cur, company_id)
    if not access:
        return None
    account_number = config.get('account_number', '')
    keywords = get_purpose_keywords(config)

    all_operations: List[Dict[str, Any]] = []
    cursor = None
    previous_cursor = None

    for _ in range(10):
        data = fetch_tbank_statement(
            access_token=access['access_token'],
            account_number=account_number,
            date_from=date_from,
            date_to=date_to,
            cursor=cursor
        )
        if data is None:
            return None if not all_operations else all_operations

        for op in data.get('operations', []):
            purpose = operation_purpose_text(op)
            if not matches_keywords(purpose, keywords):
                continue

            direction = 'in' if op.get('typeOfOperation') == 'Credit' else 'out'
            counterparty = op.get('counterParty', {}) or {}
            all_operations.append(normalize_tx(
                external_id=op.get('operationId'),
                operation_date=op.get('operationDate'),
                amount=op.get('operationAmount'),
                direction=direction,
                counterparty_name=counterparty.get('name'),
                counterparty_inn=counterparty.get('inn'),
                purpose=purpose,
                raw=op
            ))

        cursor = data.get('nextCursor')
        # Банк иногда отдаёт один и тот же cursor повторно -
        # останавливаемся, если пагинация не продвигается, чтобы не зациклиться.
        if not cursor or cursor == previous_cursor:
            break
        previous_cursor = cursor

    return all_operations


def fetch_tochka_statement_window(api_token: str, account_id: str, base_url: str,
                                   start_date: str, end_date: str, deadline: float,
                                   pending_id: Optional[str] = None) -> tuple:
    '''
    Одно окно Init Statement -> поллинг Get Statement для периода [start_date, end_date]
    (обе даты 'YYYY-MM-DD'). deadline - time.monotonic(), после которого поллинг
    прекращается независимо от статуса (используется, чтобы уложиться в таймаут
    Cloud Function при нескольких окнах подряд - см. fetch_tochka_account_statement).
    pending_id - выписка, заказанная прошлым вызовом и не успевшая сформироваться:
    повторно её не заказываем, а дожидаемся готовности.
    Returns: (transactions | None, statement_id | None - если ещё не готова)
    '''
    if pending_id:
        txs, status_code = poll_tochka_statement(api_token, account_id, base_url, pending_id, deadline)
        if txs is not None:
            return txs, None
        if status_code is None:
            return None, pending_id
        # Выписка у банка пропала/устарела - заказываем заново.
    init_req = urllib.request.Request(
        f'{base_url}/statements',
        data=json.dumps({
            'Data': {
                'Statement': {
                    'accountId': account_id,
                    'startDateTime': f'{start_date}T00:00:00Z',
                    'endDateTime': f'{end_date}T00:00:00Z'
                }
            }
        }).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(init_req, timeout=15, context=TOCHKA_SSL_CONTEXT) as response:
            init_data = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f'[DEBUG] Tochka init statement HTTP {e.code}: {(e.read().decode("utf-8") if e.fp else "")[:800]}')
        return None, None
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f'[DEBUG] Tochka init statement error: {str(e)}')
        return None, None

    statement_id = init_data.get('Data', {}).get('Statement', {}).get('statementId')
    if not statement_id:
        print(f'[DEBUG] Tochka init statement: no statementId in response: {json.dumps(init_data)[:800]}')
        return None, None

    txs, _ = poll_tochka_statement(api_token, account_id, base_url, statement_id, deadline)
    if txs is None:
        print(f'[DEBUG] Tochka statement {start_date}..{end_date} not Ready yet, will pick up next run ({statement_id})')
        return None, statement_id
    return txs, None


def poll_tochka_statement(api_token: str, account_id: str, base_url: str,
                          statement_id: str, deadline: float) -> tuple:
    '''Ждёт готовности выписки. Returns: (transactions | None, http_error_code | None).'''
    get_url = f'{base_url}/accounts/{account_id}/statements/{statement_id}'
    get_req = urllib.request.Request(get_url, headers={'Authorization': f'Bearer {api_token}'})
    while True:
        try:
            with urllib.request.urlopen(get_req, timeout=15, context=TOCHKA_SSL_CONTEXT) as response:
                statement_data = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            print(f'[DEBUG] Tochka get statement HTTP {e.code}: {(e.read().decode("utf-8") if e.fp else "")[:800]}')
            return None, e.code
        except (urllib.error.URLError, json.JSONDecodeError) as e:
            print(f'[DEBUG] Tochka get statement error: {str(e)}')
            return None, None

        statements = statement_data.get('Data', {}).get('Statement', [])
        statement = statements[0] if isinstance(statements, list) and statements else statements
        status = statement.get('status') if isinstance(statement, dict) else None
        if status == 'Ready':
            return statement.get('Transaction', []), None
        if time.monotonic() + 0.5 >= deadline:
            return None, None
        time.sleep(0.5)


def fetch_tochka_account_statement(cur, integration_id: int, company_id: int, config: Dict[str, Any],
                                    date_from: str, date_to: str) -> Optional[List[Dict[str, Any]]]:
    '''
    Точка Банк отдаёт выписку асинхронно: сначала Init Statement (заказ выписки),
    затем поллинг Get Statement пока статус не станет Ready.
    https://developers.tochka.com/docs/tochka-api/opisanie-metodov/vypiski

    Особенности реального API (отличаются от типичного Open Banking, проверено
    прямыми запросами к enter.tochka.com):
    - тело Init Statement должно быть обёрнуто в {"Data": {"Statement": {...}}},
      а не плоским объектом - иначе 400 "Field Data : Field required";
    - startDateTime/endDateTime обязаны быть датами с нулевым временем
      (полночь UTC) - "23:59:59" в конце дня Точка отклоняет как невалидную
      дату ("Datetimes provided to dates should have zero time");
    - Get Statement оборачивает результат в Data.Statement как МАССИВ из
      одного элемента (не объект), внутри - статус и список Transaction;
    - КЛЮЧЕВОЕ: время формирования выписки у Точки растёт нелинейно с длиной
      периода - окно в 7 дней готово за ~1-2 сек, а окно в 30 дней может
      идти 15-20+ сек (проверено прямыми запросами), что не укладывается в
      таймаут Cloud Function. При этом кнопка "Синхронизировать сейчас" и
      диалог дозагрузки по умолчанию запрашивают именно последние 30 дней -
      без разбивки на части выписка просто не успевала стать Ready, функция
      возвращала "Не удалось получить выписку от банка", и НИ ОДНА операция
      (ни приходы, ни расходы) за весь период не сохранялась. Поэтому период
      здесь режется на недельные окна и запрашивается ПАРАЛЛЕЛЬНО (свой
      statementId на каждое окно, запросы независимы) - иначе даже недельные
      окна одно за другим на месячном периоде не укладываются в таймаут.
    '''
    # Чистим невидимые символы (BOM, zero-width space), которые иногда
    # попадают при копировании токена - иначе latin-1 кодировка HTTP-заголовков
    # падает с UnicodeEncodeError до отправки запроса. См. tochka-accounts-list.
    api_token = re.sub(r'[^\x21-\x7e]', '', config.get('api_token', ''))
    if config.get('auth_method') == 'oauth':
        api_token, oauth_error = tochka_oauth.get_access_token(cur, company_id)
        if not api_token:
            print(f'[tochka] oauth token unavailable for company {company_id}: {oauth_error}')
            return None
    account_id = config.get('account_number', '')
    keywords = get_purpose_keywords(config)
    base_url = 'https://enter.tochka.com/uapi/open-banking/v1.0'

    start_date = datetime.fromisoformat(date_from[:10])
    # endDateTime у Точки НЕ включает сам день (полночь = начало дня), поэтому
    # чтобы последний выбранный день попал в выписку, сдвигаем конец на +1 день.
    end_date = datetime.fromisoformat(date_to[:10]) + timedelta(days=1)

    WINDOW_DAYS = 7
    # Общий бюджет на все окна с запасом под остаток работы функции (batch-вставка
    # в БД, разбор JSON) - таймаут Cloud Function 5 сек по умолчанию, оставляем запас.
    deadline = time.monotonic() + 4.0

    windows: List[tuple] = []
    cursor = start_date
    while cursor < end_date:
        window_end = min(cursor + timedelta(days=WINDOW_DAYS), end_date)
        windows.append((cursor.strftime('%Y-%m-%d'), window_end.strftime('%Y-%m-%d')))
        cursor = window_end

    # Заказанные прошлыми вызовами, но не успевшие сформироваться выписки (окно -> statementId).
    pending: Dict[str, str] = dict(config.get('tochka_pending_statements') or {})
    raw_transactions: List[Dict[str, Any]] = []
    any_window_succeeded = False
    still_pending: Dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(windows) or 1)) as executor:
        futures = [
            (f'{win_start}_{win_end}', executor.submit(
                fetch_tochka_statement_window, api_token, account_id, base_url, win_start, win_end, deadline,
                pending.get(f'{win_start}_{win_end}')))
            for win_start, win_end in windows
        ]
        for key, future in futures:
            window_tx, pending_id = future.result()
            if window_tx is not None:
                raw_transactions.extend(window_tx)
                any_window_succeeded = True
            elif pending_id:
                still_pending[key] = pending_id

    if still_pending != pending:
        cur.execute('''
            UPDATE t_p83864310_fintech_payment_reco.user_integrations
            SET config = jsonb_set(COALESCE(config, '{}'::jsonb), '{tochka_pending_statements}', %s::jsonb)
            WHERE id = %s
        ''', (json.dumps(still_pending), integration_id))
        cur.connection.commit()

    if not any_window_succeeded:
        return None

    result = []
    for tx in raw_transactions:
        purpose = tx.get('description') or ''
        if not matches_keywords(purpose, keywords):
            continue

        direction = 'in' if tx.get('creditDebitIndicator') == 'Credit' else 'out'
        party = tx.get('DebtorParty') if direction == 'in' else tx.get('CreditorParty')
        result.append(normalize_tx(
            external_id=tx.get('transactionId') or tx.get('paymentId'),
            operation_date=tx.get('documentProcessDate'),
            amount=float(tx.get('Amount', {}).get('amount', 0)),
            direction=direction,
            counterparty_name=(party or {}).get('name'),
            counterparty_inn=(party or {}).get('inn'),
            purpose=purpose,
            raw=tx
        ))

    return result


# Реестр обработчиков по провайдеру. Модульбанк требует отдельного согласования
# формата API и пока не подключён - явно возвращаем понятную ошибку вместо того,
# чтобы притворяться, что данные загружены.
STATEMENT_FETCHERS = {
    'tbank_account': fetch_tbank_account_statement,
    'tochka_account': fetch_tochka_account_statement
}


def _handle(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''
    Ручная синхронизация банковской выписки по кнопке "Синхронизировать сейчас".
    Это второй слой обработки: сюда попадают только операции, назначение платежа
    которых содержит хотя бы одно из ключевых слов настройки purpose_keywords
    (или все операции, если ключевые слова не заданы) - остальное отсекается
    ещё на этапе получения выписки от банка.
    Args: integration_id, date_from (ISO, опционально), date_to (ISO, опционально)
    Returns: количество загруженных и новых транзакций
    '''

    method = event.get('httpMethod', 'POST')

    if method == 'OPTIONS':
        return {'statusCode': 200, 'headers': CORS_HEADERS, 'body': '', 'isBase64Encoded': False}

    if method != 'POST':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }

    body_data = json.loads(event.get('body') or '{}')
    integration_id = body_data.get('integration_id')

    if not integration_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'integration_id required'}),
            'isBase64Encoded': False
        }

    date_from = body_data.get('date_from') or (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%dT00:00:00Z')
    date_to = body_data.get('date_to') or datetime.now().strftime('%Y-%m-%dT23:59:59Z')

    dsn = os.environ['DATABASE_URL']
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()

    try:
        cur.execute('''
            SELECT ui.config, ui.company_id, p.slug
            FROM t_p83864310_fintech_payment_reco.user_integrations ui
            JOIN t_p83864310_fintech_payment_reco.integration_providers p ON p.id = ui.provider_id
            WHERE ui.id = %s AND ui.status = 'active'
        ''', (integration_id,))

        row = cur.fetchone()
        if not row:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Integration not found'}),
                'isBase64Encoded': False
            }

        config, company_id, provider_slug = row
        config = json.loads(config) if isinstance(config, str) else (config or {})

        fetcher = STATEMENT_FETCHERS.get(provider_slug)
        if not fetcher:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({
                    'success': False,
                    'error': f'Синхронизация для {provider_slug} пока не реализована'
                }),
                'isBase64Encoded': False
            }

        transactions = fetcher(cur, integration_id, company_id, config, date_from, date_to)
        if transactions is None:
            cur.execute('SELECT config FROM t_p83864310_fintech_payment_reco.user_integrations WHERE id = %s', (integration_id,))
            fresh = cur.fetchone()
            fresh_cfg = (json.loads(fresh[0]) if isinstance(fresh[0], str) else fresh[0]) if fresh and fresh[0] else {}
            waiting = bool(fresh_cfg.get('tochka_pending_statements'))
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'success': False, 'pending': waiting,
                                    'error': 'Банк ещё формирует выписку - заберём при следующем запуске' if waiting
                                    else 'Не удалось получить выписку от банка'}),
                'isBase64Encoded': False
            }

        # Вставляем все транзакции одним batch-запросом (execute_values), а не
        # по одной с отдельным round-trip к БД на каждую - при выписке в
        # сотни операций (обычное дело для Точки за 30 дней) последовательные
        # INSERT'ы не укладывались в таймаут функции (5 сек), и вся
        # синхронизация падала с JobExecutionTimeoutExceeded, не сохранив
        # ничего (транзакция БД откатывалась целиком).
        rows = [(
            integration_id, company_id, provider_slug, tx['external_id'],
            tx['operation_date'], tx['amount'], tx['direction'],
            tx['counterparty_name'], tx['counterparty_inn'], tx['purpose'],
            json.dumps(tx['raw']), 'cron' if body_data.get('cron_tick') else 'manual'
        ) for tx in transactions]

        inserted_count = 0
        if rows:
            inserted_ids = psycopg2.extras.execute_values(
                cur,
                '''
                INSERT INTO t_p83864310_fintech_payment_reco.bank_statement_transactions (
                    integration_id, company_id, provider_slug, external_transaction_id,
                    operation_date, amount, direction, counterparty_name, counterparty_inn,
                    purpose, raw_data, origin
                ) VALUES %s
                ON CONFLICT (integration_id, external_transaction_id) DO NOTHING
                RETURNING id
                ''',
                rows,
                fetch=True
            )
            inserted_count = len(inserted_ids)

        commission_rows = process_acquiring_settlements(cur, integration_id, company_id, provider_slug, config)

        cur.execute('''
            UPDATE t_p83864310_fintech_payment_reco.user_integrations
            SET last_synced_at = NOW(), updated_at = NOW()
            WHERE id = %s
        ''', (integration_id,))

        conn.commit()

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'success': True,
                'total_transactions': len(transactions),
                'inserted': inserted_count,
                'commission_rows': commission_rows
            }),
            'isBase64Encoded': False
        }

    except Exception as e:
        conn.rollback()
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)}),
            'isBase64Encoded': False
        }
    finally:
        cur.close()
        conn.close()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    '''Точка входа: обработка запроса + итог для админки, если вызвал планировщик.'''
    denied = guard(event)
    if denied:
        return denied

    resp = _handle(event, context)
    if event.get('httpMethod', 'POST') == 'POST':
        record_cron_run(event, resp, 'bank', 'inserted')
    return resp

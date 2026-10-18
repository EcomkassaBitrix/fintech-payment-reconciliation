import time
from typing import Any, Callable

import psycopg2


def is_transient(e: Exception) -> bool:
    '''Временный сбой базы: перегрузка («rate limit exceeded»), обрыв соединения, отмена запроса.'''
    if isinstance(e, (psycopg2.OperationalError, psycopg2.InterfaceError)):
        return True
    return 'rate limit' in str(e).lower()


def safe_rollback(conn) -> None:
    try:
        conn.rollback()
    except Exception:
        pass


def with_retry(conn, fn: Callable[[], Any], tries: int = 4, base_delay: float = 0.3) -> Any:
    '''
    Выполняет fn и фиксирует транзакцию. При временном сбое базы - откат и повтор
    с нарастающей паузой (0.3, 0.6, 1.2 с), чтобы переждать всплеск нагрузки.
    '''
    for attempt in range(tries):
        try:
            result = fn()
            conn.commit()
            return result
        except Exception as e:
            safe_rollback(conn)
            if not is_transient(e) or attempt == tries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


def connect(dsn: str, tries: int = 3):
    for attempt in range(tries):
        try:
            return psycopg2.connect(dsn)
        except psycopg2.OperationalError:
            if attempt == tries - 1:
                raise
            time.sleep(0.4 * (2 ** attempt))

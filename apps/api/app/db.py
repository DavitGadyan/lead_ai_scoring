from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


@contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    conn = psycopg.connect(settings.database_url, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()

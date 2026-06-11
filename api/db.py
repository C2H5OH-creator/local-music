import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from api.settings import get_settings


@contextmanager
def get_connection() -> Iterator[psycopg.Connection[dict[str, Any]]]:
    settings = get_settings()
    has_discrete_database_settings = any(
        key in os.environ
        for key in (
            "DATABASE_HOST",
            "DATABASE_PORT",
            "DATABASE_NAME",
            "DATABASE_USER",
            "DATABASE_PASSWORD",
        )
    )
    if settings.database_url and not has_discrete_database_settings:
        connection = psycopg.connect(settings.database_url, row_factory=dict_row)
    else:
        connection = psycopg.connect(
            host=settings.database_host,
            port=settings.database_port,
            dbname=settings.database_name,
            user=settings.database_user,
            password=settings.database_password,
            row_factory=dict_row,
        )

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

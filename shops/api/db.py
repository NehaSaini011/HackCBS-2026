
import os
import time
from contextvars import ContextVar

import psycopg
from psycopg.rows import dict_row


# Holds the database time accumulated during the current request.
request_db_latency = ContextVar("request_db_latency", default=None)


class TimedConnection:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self.connection.__exit__(
            exc_type, exc_value, traceback
        )

    def execute(self, *args, **kwargs):
        start = time.perf_counter()

        try:
            return self.connection.execute(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000

            accumulator = request_db_latency.get()
            if accumulator is not None:
                accumulator[0] += elapsed_ms


def get_connection(database_env: str):
    database_url = os.getenv(database_env)

    if not database_url:
        raise RuntimeError(
            f"Missing database environment variable: {database_env}"
        )

    connection = psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=5
    )

    return TimedConnection(connection)

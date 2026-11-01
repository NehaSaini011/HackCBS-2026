
import asyncio
import os
import time

import psycopg
from fastapi import Request

from shops.api.db import request_db_latency


def install_metrics(app, shop_name: str, database_env: str):
    """
    Install request monitoring and a background metrics writer
    for one shop.
    """

    metrics_buffer = []
    buffer_lock = asyncio.Lock()
    flush_task = None

    async def flush_metrics():
        async with buffer_lock:
            if not metrics_buffer:
                return

            batch = metrics_buffer.copy()
            metrics_buffer.clear()

        database_url = os.getenv(database_env)
        if not database_url:
            print(f"[{shop_name}] Missing environment variable: {database_env}")
            return

        try:
            def write_batch():
                with psycopg.connect(database_url) as conn:
                    with conn.cursor() as cur:
                        cur.executemany(
                            """
                            INSERT INTO request_metrics
                            (endpoint, method, status_code,
                            total_latency_ms, db_latency_ms)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            batch
                        )
            await asyncio.to_thread(write_batch)

        except Exception as exc:
            # Put failed records back so they can be retried.
            async with buffer_lock:
                metrics_buffer[0:0] = batch

            print(f"[{shop_name}] Metrics flush failed: {exc}")

    async def background_writer():
        while True:
            await asyncio.sleep(5)
            await flush_metrics()

    @app.middleware("http")
    async def collect_request_metrics(request: Request, call_next):
        nonlocal flush_task

        # Start the metrics writer on the first request.
        if flush_task is None:
            flush_task = asyncio.create_task(background_writer())
        start = time.perf_counter()
        db_time = [0.0]

        token = request_db_latency.set(db_time)
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response

        except Exception:
            raise

        finally:
            total_latency = (time.perf_counter() - start) * 1000
            request_db_latency.reset(token)

            route = request.scope.get("route")
            endpoint = getattr(route, "path", request.url.path)

            record = (
                endpoint,
                request.method,
                status_code,
                total_latency,
                db_time[0]
            )

            async with buffer_lock:
                metrics_buffer.append(record)

    
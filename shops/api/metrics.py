
import asyncio
import os
import time

import psycopg
from fastapi import Request, Response
from prometheus_client import (
    Counter,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

from shops.api.db import request_db_latency


# Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["shop", "method", "endpoint", "status"]
)

REQUEST_ERRORS = Counter(
    "http_requests_errors_total",
    "Total HTTP error responses (4xx and 5xx)",
    ["shop", "method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["shop", "method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25,
             0.5, 0.75, 1.0, 2.5, 5.0, 10.0)
)


def install_metrics(app, shop_name: str, database_env: str):
    """
    Install request monitoring, Prometheus metrics,
    and a background PostgreSQL metrics writer.
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
            async with buffer_lock:
                metrics_buffer[0:0] = batch
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
            async with buffer_lock:
                metrics_buffer[0:0] = batch

            print(f"[{shop_name}] Metrics flush failed: {exc}")

    async def background_writer():
        while True:
            await asyncio.sleep(5)
            await flush_metrics()

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST
        )

    @app.middleware("http")
    async def collect_request_metrics(request: Request, call_next):
        nonlocal flush_task

        # Do not count Prometheus scraping as application traffic.
        if request.url.path == "/metrics":
            return await call_next(request)

        if flush_task is None:
            flush_task = asyncio.create_task(background_writer())

        start = time.perf_counter()
        db_time = [0.0]
        status_code = 500

        token = request_db_latency.set(db_time)

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response

        finally:
            duration = time.perf_counter() - start
            total_latency_ms = duration * 1000

            request_db_latency.reset(token)

            route = request.scope.get("route")
            endpoint = getattr(route, "path", request.url.path)

            method = request.method
            status = str(status_code)

            REQUEST_COUNT.labels(
                shop_name, method, endpoint, status
            ).inc()

            REQUEST_LATENCY.labels(
                shop_name, method, endpoint
            ).observe(duration)

            if status_code >= 400:
                REQUEST_ERRORS.labels(
                    shop_name, method, endpoint, status
                ).inc()

            record = (
                endpoint,
                method,
                status_code,
                total_latency_ms,
                db_time[0]
            )

            async with buffer_lock:
                metrics_buffer.append(record)

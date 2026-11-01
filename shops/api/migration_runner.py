import os
import secrets
from pathlib import Path

import psycopg


BASE_DIR = Path(__file__).resolve().parents[1]


def run_shop_migration(shop: str, database_env: str, migration: str):
    database_url = os.getenv(database_env)

    if not database_url:
        raise RuntimeError(f"Missing {database_env}")

    migration_file = BASE_DIR / "migrations" / shop / migration

    if not migration_file.exists():
        raise FileNotFoundError(f"Migration not found: {migration_file}")

    sql = migration_file.read_text(encoding="utf-8")

    # CONCURRENTLY operations require autocommit.
    with psycopg.connect(
        database_url,
        autocommit=True,
        connect_timeout=5
    ) as conn:
        for statement in sql.split(";"):
            statement = statement.strip()

            if statement:
                conn.execute(statement)

    return {"status": "success", "migration": migration}


def verify_admin_token(provided_token: str | None, env_name: str):
    expected_token = os.getenv(env_name)

    if not expected_token:
        raise RuntimeError(f"{env_name} is not configured")

    if not provided_token or not secrets.compare_digest(
        provided_token, expected_token
    ):
        return False

    return True
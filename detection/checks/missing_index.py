
import os
import psycopg

SHOPS = {
    "a": {
        "database_env": "PINECART_DATABASE_URL",
        "table": "orders",
        "columns": ["customer_id", "created_at"],
    },
    "b": {
        "database_env": "TEALBOX_DATABASE_URL",
        "table": "purchases",
        "columns": ["buyer_id", "placed_at"],
    },
}


def has_required_index(conn, table, columns):
    # Match an index with the required leading columns and DESC on column 2.
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = %s
              AND (
                  indexdef ILIKE %s
                  OR indexdef ILIKE %s
              )
        )
    """
    first, second = columns

    patterns = (
        f"%({first}, {second} DESC)%",
        f'%("{first}", "{second}" DESC)%',
    )

    return conn.execute(query, (table, *patterns)).fetchone()[0]


def check_missing_index():
    findings = []

    for shop, config in SHOPS.items():
        database_url = os.getenv(
            "PINECART_DATABASE_URL" if shop == "a"
            else "TEALBOX_DATABASE_URL"
        )

        if not database_url:
            print(f"Skipping Shop {shop.upper()}: database URL not configured")
            continue

        with psycopg.connect(database_url, connect_timeout=5) as conn:
            exists = has_required_index(
                conn,
                config["table"],
                config["columns"],
            )

        if not exists:
            findings.append({
                "shop": shop,
                "source": "postgresql",
                "test": "missing_index",
                "severity": "critical",
                "summary": (
                    f"Required index coverage missing on "
                    f"{config['table']} ({config['columns'][0]}, "
                    f"{config['columns'][1]} DESC)"
                ),
                "raw": {
                    "table": config["table"],
                    "required_columns": config["columns"],
                    "second_column_order": "DESC",
                },
            })

    return findings

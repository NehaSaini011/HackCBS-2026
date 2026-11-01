import os
import psycopg

SHOPS = {
    "a": {
        "database_env": "PINECART_DATABASE_URL",
        "table": "orders",
        "index": "idx_orders_customer_created",
    },
    "b": {
        "database_env": "TEALBOX_DATABASE_URL",
        "table": "purchases",
        "index": "idx_purchases_buyer_placed",
    },
}


def check_missing_index():
    findings = []

    for shop, config in SHOPS.items():
        database_url = os.getenv(config["database_env"])

        if not database_url:
            print(f"Skipping Shop {shop.upper()}: database URL not configured")
            continue

        with psycopg.connect(database_url, connect_timeout=5) as conn:
            result = conn.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = %s
                      AND indexname = %s
                )
                """,
                (config["table"], config["index"]),
            ).fetchone()

        if not result[0]:
            findings.append({
                "shop": shop,
                "source": "postgresql",
                "test": "missing_index",
                "severity": "critical",
                "summary": f"Required index {config['index']} is missing",
                "raw": {
                    "table": config["table"],
                    "expected_index": config["index"],
                },
            })

    return findings
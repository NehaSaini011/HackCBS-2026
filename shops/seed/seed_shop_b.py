
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
from faker import Faker


fake = Faker()
Faker.seed(202)
rng = random.Random(202)

DATABASE_URL = os.getenv(
    "TEALBOX_DATABASE_URL",
    "postgresql://postgres:YOUR_PASSWORD@localhost:5432/tealbox_db"
)

BUYER_COUNT = 100
PRODUCT_COUNT = 20
PURCHASE_COUNT = 500


def insert_many(cur, sql, rows, columns_per_row):
    """Insert multiple rows and return their generated IDs."""
    if not rows:
        return []

    placeholders = "(" + ",".join(["%s"] * columns_per_row) + ")"
    values_sql = ",".join([placeholders] * len(rows))
    params = [value for row in rows for value in row]

    cur.execute(sql.format(values=values_sql), params)
    return [row[0] for row in cur.fetchall()]


def seed():
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=730)

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:

            # 1. Create buyers
            buyer_rows = []

            for i in range(BUYER_COUNT):
                buyer_rows.append((
                    fake.name(),
                    f"tealbox_buyer_{i}@example.com",
                    fake.date_time_between(
                        start_date=start_date,
                        end_date=now,
                        tzinfo=timezone.utc
                    )
                ))

            buyer_ids = insert_many(
                cur,
                """
                INSERT INTO buyers
                    (full_name, email_address, registered_at)
                VALUES {values}
                RETURNING id
                """,
                buyer_rows,
                3
            )

            # 2. Create products
            categories = [
                "Electronics", "Fashion", "Home", "Books", "Sports"
            ]

            product_rows = []

            for _ in range(PRODUCT_COUNT):
                product_rows.append((
                    fake.catch_phrase(),
                    fake.sentence(),
                    rng.choice(categories),
                    Decimal(str(round(rng.uniform(10, 1000), 2))),
                    rng.randint(0, 500),
                    fake.date_time_between(
                        start_date=start_date,
                        end_date=now,
                        tzinfo=timezone.utc
                    )
                ))

            product_ids = insert_many(
                cur,
                """
                INSERT INTO products
                    (product_name, details, product_type, unit_price,
                     available_quantity, added_at)
                VALUES {values}
                RETURNING id
                """,
                product_rows,
                6
            )

            product_prices = {
                product_id: product[3]
                for product_id, product in zip(product_ids, product_rows)
            }

            # 3. Prepare purchases and their items
            purchase_specs = []
            purchase_rows = []
            statuses = [
                "pending", "processing", "shipped", "delivered"
            ]

            for _ in range(PURCHASE_COUNT):
                selected_products = rng.sample(
                    product_ids,
                    rng.randint(1, min(3, len(product_ids)))
                )

                items = []
                total = Decimal("0.00")

                for product_id in selected_products:
                    quantity = rng.randint(1, 4)
                    price = product_prices[product_id]

                    items.append((product_id, quantity, price))
                    total += price * quantity

                buyer_id = rng.choice(buyer_ids)

                placed_at = fake.date_time_between(
                    start_date=start_date,
                    end_date=now,
                    tzinfo=timezone.utc
                )

                purchase_rows.append((
                    buyer_id,
                    rng.choice(statuses),
                    total,
                    placed_at
                ))

                purchase_specs.append(items)

            # 4. Insert purchases
            purchase_ids = insert_many(
                cur,
                """
                INSERT INTO purchases
                    (buyer_id, purchase_status, purchase_total, placed_at)
                VALUES {values}
                RETURNING id
                """,
                purchase_rows,
                4
            )

            # 5. Insert purchase items
            purchase_item_rows = []

            for purchase_id, items in zip(purchase_ids, purchase_specs):
                for product_id, quantity, price in items:
                    purchase_item_rows.append((
                        purchase_id,
                        product_id,
                        quantity,
                        price
                    ))

            insert_many(
                cur,
                """
                INSERT INTO purchase_items
                    (purchase_id, product_id, item_quantity,
                     price_at_purchase)
                VALUES {values}
                RETURNING id
                """,
                purchase_item_rows,
                4
            )

            # 6. Create basket items
            basket_rows = []

            for buyer_id in buyer_ids:
                selected_products = rng.sample(
                    product_ids,
                    rng.randint(1, min(2, len(product_ids)))
                )

                for product_id in selected_products:
                    basket_rows.append((
                        buyer_id,
                        product_id,
                        rng.randint(1, 4),
                        now
                    ))

            insert_many(
                cur,
                """
                INSERT INTO basket_items
                    (buyer_id, product_id, item_quantity, added_at)
                VALUES {values}
                RETURNING id
                """,
                basket_rows,
                4
            )

        conn.commit()

    print("Tealbox seed completed!")
    print(f"Buyers: {len(buyer_ids)}")
    print(f"Products: {len(product_ids)}")
    print(f"Purchases: {len(purchase_ids)}")
    print(f"Purchase items: {len(purchase_item_rows)}")
    print(f"Basket items: {len(basket_rows)}")


if __name__ == "__main__":
    seed()

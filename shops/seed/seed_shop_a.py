
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg
from faker import Faker

# Reproducible data: running with the same seed gives the same fake data.
fake = Faker()
Faker.seed(101)
rng = random.Random(101)

DATABASE_URL = os.getenv(
    "PINECART_DATABASE_URL",
    "postgresql://postgres:YOUR_PASSWORD@localhost:5432/pinecart_db"
)

# Start small. We will increase these after testing.
CUSTOMER_COUNT = 100
PRODUCT_COUNT = 20
ORDER_COUNT = 500


def insert_many(cur, sql, rows, columns_per_row):
    """Insert a batch and return generated identity IDs."""
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

            # 1. Customers: parent records for orders and cart items.
            customers = [
                (
                    fake.name(),
                    f"pinecart_customer_{i}@example.com",
                    fake.date_time_between(
                        start_date=start_date,
                        end_date=now,
                        tzinfo=timezone.utc
                    )
                )
                for i in range(CUSTOMER_COUNT)
            ]

            customer_ids = insert_many(
                cur,
                """
                INSERT INTO customers (name, email, created_at)
                VALUES {values}
                RETURNING id
                """,
                customers,
                3
            )

            # 2. Products: parent records for order_items and cart_items.
            categories = ["Electronics", "Fashion", "Home", "Books", "Sports"]
            products = [
                (
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
                )
                for _ in range(PRODUCT_COUNT)
            ]

            product_ids = insert_many(
                cur,
                """
                INSERT INTO products
                    (name, description, category, price, stock, created_at)
                VALUES {values}
                RETURNING id
                """,
                products,
                6
            )
            product_prices = {
                product_id: product[3]
                for product_id, product in zip(product_ids, products)
            }

            # 3. Orders: each order belongs to an existing customer.
            order_rows = []
            for _ in range(ORDER_COUNT):
                order_rows.append((
                    rng.choice(customer_ids),
                    rng.choice(["pending", "processing", "shipped", "delivered"]),
                    Decimal("0.00"),
                    fake.date_time_between(
                        start_date=start_date,
                        end_date=now,
                        tzinfo=timezone.utc
                    )
                ))

            order_ids = insert_many(
                cur,
                """
                INSERT INTO orders
                    (customer_id, status, total_amount, created_at)
                VALUES {values}
                RETURNING id
                """,
                order_rows,
                4
            )

            # 4. Order items: each item references an order and a product.
            item_rows = []
            for order_id in order_ids:
                chosen_products = rng.sample(
                    product_ids,
                    k=rng.randint(1, min(3, len(product_ids)))
                )
                for product_id in chosen_products:
                    quantity = rng.randint(1, 4)
                    price = product_prices[product_id]
                    item_rows.append((
                        order_id,
                        product_id,
                        quantity,
                        price
                    ))

            insert_many(
                cur,
                """
                INSERT INTO order_items
                    (order_id, product_id, quantity, unit_price)
                VALUES {values}
                RETURNING id
                """,
                item_rows,
                4
            )

            # 5. Cart items: one product per customer, as required
            # by UNIQUE(customer_id, product_id).
            cart_rows = []
            for customer_id in customer_ids:
                chosen_products = rng.sample(
                    product_ids,
                    k=rng.randint(1, min(2, len(product_ids)))
                )
                for product_id in chosen_products:
                    cart_rows.append((
                        customer_id,
                        product_id,
                        rng.randint(1, 4),
                        now
                    ))

            insert_many(
                cur,
                """
                INSERT INTO cart_items
                    (customer_id, product_id, quantity, created_at)
                VALUES {values}
                RETURNING id
                """,
                cart_rows,
                4
            )

            print("Pinecart seed completed!")
            print(f"Customers: {len(customer_ids)}")
            print(f"Products: {len(product_ids)}")
            print(f"Orders: {len(order_ids)}")
            print(f"Order items: {len(item_rows)}")
            print(f"Cart items: {len(cart_rows)}")


if __name__ == "__main__":
    seed()

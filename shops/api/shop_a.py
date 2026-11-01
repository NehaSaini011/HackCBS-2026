from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from shops.api.metrics import install_metrics
from shops.api.db import get_connection
from shops.api.migration_runner import (
    run_shop_migration,
    verify_admin_token
)

app = FastAPI(title="Pinecart API", version="2.2")
install_metrics(app, "pinecart", "PINECART_DATABASE_URL")
@app.post("/admin/deploy")
def deploy_v23(x_admin_token: str | None = Header(None, alias="X-Admin-Token")):
    if not verify_admin_token(x_admin_token, "PINECART_ADMIN_TOKEN"):
        raise HTTPException(status_code=403, detail="Invalid admin token")

    try:
        result = run_shop_migration(
            "shop_a",
            "PINECART_DATABASE_URL",
            "003_deploy_v23.sql"
        )
        return {"shop": "pinecart", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/reset")
def reset_v22(x_admin_token: str | None = Header(None, alias="X-Admin-Token")):
    if not verify_admin_token(x_admin_token, "PINECART_ADMIN_TOKEN"):
        raise HTTPException(status_code=403, detail="Invalid admin token")

    try:
        result = run_shop_migration(
            "shop_a",
            "PINECART_DATABASE_URL",
            "004_reset_v22.sql"
        )
        return {"shop": "pinecart", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CartItemRequest(BaseModel):
    customer_id: int
    product_id: int
    quantity: int = Field(gt=0, le=100)


# 1. Basic liveness check: does the API process respond?
@app.get("/health")
def health():
    return {"status": "alive", "shop": "pinecart"}


# 2. Database readiness check
@app.get("/ready")
def ready():
    try:
        with get_connection("PINECART_DATABASE_URL") as conn:
            conn.execute("SELECT 1")
        return {"status": "ready", "database": "connected"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database is not ready"
        )


# 3. Get products, with optional search and category filters
@app.get("/products")
def get_products(
    page: int = 1,
    q: str | None = None,
    category: str | None = None
):
    if page < 1:
        raise HTTPException(400, "Page must be at least 1")

    limit = 20
    offset = (page - 1) * limit

    query = """
        SELECT id, name, description, category, price, stock
        FROM products
        WHERE (%s::text IS NULL OR name ILIKE %s)
        AND (%s::text IS NULL OR category = %s)
        ORDER BY id
        LIMIT %s OFFSET %s
    """

    search = f"%{q}%" if q else None

    with get_connection("PINECART_DATABASE_URL") as conn:
        rows = conn.execute(
            query,
            (q, search, category, category, limit, offset)
        ).fetchall()

    return {"page": page, "products": rows}


# 4. Get one product by ID
@app.get("/products/{product_id}")
def get_product(product_id: int):
    with get_connection("PINECART_DATABASE_URL") as conn:
        row = conn.execute(
            """
            SELECT id, name, description, category, price, stock
            FROM products
            WHERE id = %s
            """,
            (product_id,)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Product not found")

    return row


# 5. View a customer's cart
@app.get("/cart/{customer_id}")
def get_cart(customer_id: int):
    with get_connection("PINECART_DATABASE_URL") as conn:
        rows = conn.execute(
            """
            SELECT
                ci.id AS cart_item_id,
                ci.product_id,
                p.name,
                p.price,
                ci.quantity,
                p.price * ci.quantity AS subtotal
            FROM cart_items ci
            JOIN products p ON p.id = ci.product_id
            WHERE ci.customer_id = %s
            ORDER BY ci.id
            """,
            (customer_id,)
        ).fetchall()

    return {"customer_id": customer_id, "items": rows}


# 6. Add a product to the cart
@app.post("/cart/items")
def add_cart_item(item: CartItemRequest):
    with get_connection("PINECART_DATABASE_URL") as conn:
        customer = conn.execute(
            "SELECT id FROM customers WHERE id = %s",
            (item.customer_id,)
        ).fetchone()

        if not customer:
            raise HTTPException(404, "Customer not found")

        product = conn.execute(
            "SELECT id FROM products WHERE id = %s",
            (item.product_id,)
        ).fetchone()

        if not product:
            raise HTTPException(404, "Product not found")

        row = conn.execute(
            """
            INSERT INTO cart_items (customer_id, product_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (customer_id, product_id)
            DO UPDATE SET quantity =
                cart_items.quantity + EXCLUDED.quantity
            RETURNING id, customer_id, product_id, quantity
            """,
            (item.customer_id, item.product_id, item.quantity)
        ).fetchone()

    return {"message": "Cart updated", "item": row}


# 7. Remove a cart item
@app.delete("/cart/items/{cart_item_id}")
def delete_cart_item(cart_item_id: int):
    with get_connection("PINECART_DATABASE_URL") as conn:
        row = conn.execute(
            """
            DELETE FROM cart_items
            WHERE id = %s
            RETURNING id
            """,
            (cart_item_id,)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Cart item not found")

    return {"message": "Cart item removed"}


# 8. Place an order using the customer's current cart
@app.post("/orders/{customer_id}")
def place_order(customer_id: int):
    with get_connection("PINECART_DATABASE_URL") as conn:
        customer = conn.execute(
            "SELECT id FROM customers WHERE id = %s",
            (customer_id,)
        ).fetchone()

        if not customer:
            raise HTTPException(404, "Customer not found")

        cart = conn.execute(
            """
            SELECT ci.product_id, ci.quantity, p.price, p.stock
            FROM cart_items ci
            JOIN products p ON p.id = ci.product_id
            WHERE ci.customer_id = %s
            FOR UPDATE OF p
            """,
            (customer_id,)
        ).fetchall()

        if not cart:
            raise HTTPException(400, "Cart is empty")

        for item in cart:
            if item["stock"] < item["quantity"]:
                raise HTTPException(
                    400,
                    f"Insufficient stock for product {item['product_id']}"
                )

        total = sum(
            (item["price"] * item["quantity"] for item in cart),
            start=0
        )

        order = conn.execute(
            """
            INSERT INTO orders (customer_id, status, total_amount)
            VALUES (%s, %s, %s)
            RETURNING id, customer_id, status, total_amount, created_at
            """,
            (customer_id, "processing", total)
        ).fetchone()

        for item in cart:
            conn.execute(
                """
                INSERT INTO order_items
                    (order_id, product_id, quantity, unit_price)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    order["id"],
                    item["product_id"],
                    item["quantity"],
                    item["price"]
                )
            )

            conn.execute(
                """
                UPDATE products
                SET stock = stock - %s
                WHERE id = %s
                """,
                (item["quantity"], item["product_id"])
            )

        conn.execute(
            "DELETE FROM cart_items WHERE customer_id = %s",
            (customer_id,)
        )

    return {"message": "Order placed", "order": order}


# 9. Customer order history — our important hot-path endpoint
@app.get("/customers/{customer_id}/orders")
def get_customer_orders(customer_id: int):
    with get_connection("PINECART_DATABASE_URL") as conn:
        customer = conn.execute(
            "SELECT id FROM customers WHERE id = %s",
            (customer_id,)
        ).fetchone()

        if not customer:
            raise HTTPException(404, "Customer not found")

        rows = conn.execute(
            """
            SELECT id, status, total_amount, created_at
            FROM orders
            WHERE customer_id = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (customer_id,)
        ).fetchall()

    return {"customer_id": customer_id, "orders": rows}


# 10. Current API version and basic status
@app.get("/status")
def status():
    with get_connection("PINECART_DATABASE_URL") as conn:
        conn.execute("SELECT 1")

    return {
        "shop": "pinecart",
        "version": app.version,
        "status": "healthy"
    }

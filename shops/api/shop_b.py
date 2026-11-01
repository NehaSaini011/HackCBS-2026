from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from shops.api.metrics import install_metrics
from shops.api.db import get_connection
from shops.api.migration_runner import (
    run_shop_migration,
    verify_admin_token
)

app = FastAPI(title="Tealbox API", version="2.2")
install_metrics(app, "tealbox", "TEALBOX_DATABASE_URL")
@app.post("/admin/deploy")
def deploy_v23(x_admin_token: str | None = Header(None, alias="X-Admin-Token")):
    if not verify_admin_token(x_admin_token, "TEALBOX_ADMIN_TOKEN"):
        raise HTTPException(status_code=403, detail="Invalid admin token")

    try:
        result = run_shop_migration(
            "shop_b",
            "TEALBOX_DATABASE_URL",
            "003_deploy_v23.sql"
        )
        return {"shop": "tealbox", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/reset")
def reset_v22(x_admin_token: str | None = Header(None, alias="X-Admin-Token")):
    if not verify_admin_token(x_admin_token, "TEALBOX_ADMIN_TOKEN"):
        raise HTTPException(status_code=403, detail="Invalid admin token")

    try:
        result = run_shop_migration(
            "shop_b",
            "TEALBOX_DATABASE_URL",
            "004_reset_v22.sql"
        )
        return {"shop": "tealbox", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    
class BasketItemRequest(BaseModel):
    buyer_id: int
    product_id: int
    quantity: int = Field(gt=0, le=100)


# 1. API liveness
@app.get("/health")
def health():
    return {"status": "alive", "shop": "tealbox"}


# 2. Database readiness
@app.get("/ready")
def ready():
    try:
        with get_connection("TEALBOX_DATABASE_URL") as conn:
            conn.execute("SELECT 1")

        return {"status": "ready", "database": "connected"}

    except Exception:
        raise HTTPException(503, "Database is not ready")


# 3. Get products with optional filters
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
        SELECT
            id, product_name, details, product_type,
            unit_price, available_quantity
        FROM products
        WHERE (%s::text IS NULL OR product_name ILIKE %s)
          AND (%s::text IS NULL OR product_type = %s)
        ORDER BY id
        LIMIT %s OFFSET %s
    """

    search = f"%{q}%" if q else None

    with get_connection("TEALBOX_DATABASE_URL") as conn:
        rows = conn.execute(
            query,
            (q, search, category, category, limit, offset)
        ).fetchall()

    return {"page": page, "products": rows}


# 4. Get one product
@app.get("/products/{product_id}")
def get_product(product_id: int):
    with get_connection("TEALBOX_DATABASE_URL") as conn:
        row = conn.execute(
            """
            SELECT id, product_name, details, product_type,
                   unit_price, available_quantity
            FROM products
            WHERE id = %s
            """,
            (product_id,)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Product not found")

    return row


# 5. View a buyer's basket
@app.get("/basket/{buyer_id}")
def get_basket(buyer_id: int):
    with get_connection("TEALBOX_DATABASE_URL") as conn:
        rows = conn.execute(
            """
            SELECT
                bi.id AS basket_item_id,
                bi.product_id,
                p.product_name,
                p.unit_price,
                bi.item_quantity,
                p.unit_price * bi.item_quantity AS subtotal
            FROM basket_items bi
            JOIN products p ON p.id = bi.product_id
            WHERE bi.buyer_id = %s
            ORDER BY bi.id
            """,
            (buyer_id,)
        ).fetchall()

    return {"buyer_id": buyer_id, "items": rows}


# 6. Add a product to the basket
@app.post("/basket/items")
def add_basket_item(item: BasketItemRequest):
    with get_connection("TEALBOX_DATABASE_URL") as conn:
        buyer = conn.execute(
            "SELECT id FROM buyers WHERE id = %s",
            (item.buyer_id,)
        ).fetchone()

        if not buyer:
            raise HTTPException(404, "Buyer not found")

        product = conn.execute(
            "SELECT id FROM products WHERE id = %s",
            (item.product_id,)
        ).fetchone()

        if not product:
            raise HTTPException(404, "Product not found")

        row = conn.execute(
            """
            INSERT INTO basket_items
                (buyer_id, product_id, item_quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (buyer_id, product_id)
            DO UPDATE SET item_quantity =
                basket_items.item_quantity + EXCLUDED.item_quantity
            RETURNING id, buyer_id, product_id, item_quantity
            """,
            (item.buyer_id, item.product_id, item.quantity)
        ).fetchone()

    return {"message": "Basket updated", "item": row}


# 7. Remove a basket item
@app.delete("/basket/items/{basket_item_id}")
def delete_basket_item(basket_item_id: int):
    with get_connection("TEALBOX_DATABASE_URL") as conn:
        row = conn.execute(
            """
            DELETE FROM basket_items
            WHERE id = %s
            RETURNING id
            """,
            (basket_item_id,)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Basket item not found")

    return {"message": "Basket item removed"}


# 8. Place a purchase using the current basket
@app.post("/purchases/{buyer_id}")
def place_purchase(buyer_id: int):
    with get_connection("TEALBOX_DATABASE_URL") as conn:
        buyer = conn.execute(
            "SELECT id FROM buyers WHERE id = %s",
            (buyer_id,)
        ).fetchone()

        if not buyer:
            raise HTTPException(404, "Buyer not found")

        basket = conn.execute(
            """
            SELECT
                bi.product_id,
                bi.item_quantity,
                p.unit_price,
                p.available_quantity
            FROM basket_items bi
            JOIN products p ON p.id = bi.product_id
            WHERE bi.buyer_id = %s
            FOR UPDATE OF p
            """,
            (buyer_id,)
        ).fetchall()

        if not basket:
            raise HTTPException(400, "Basket is empty")

        for item in basket:
            if item["available_quantity"] < item["item_quantity"]:
                raise HTTPException(
                    400,
                    f"Insufficient stock for product {item['product_id']}"
                )

        total = sum(
            (
                item["unit_price"] * item["item_quantity"]
                for item in basket
            ),
            start=0
        )

        purchase = conn.execute(
            """
            INSERT INTO purchases
                (buyer_id, purchase_status, purchase_total)
            VALUES (%s, %s, %s)
            RETURNING id, buyer_id, purchase_status,
                      purchase_total, placed_at
            """,
            (buyer_id, "processing", total)
        ).fetchone()

        for item in basket:
            conn.execute(
                """
                INSERT INTO purchase_items
                    (purchase_id, product_id, item_quantity,
                     price_at_purchase)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    purchase["id"],
                    item["product_id"],
                    item["item_quantity"],
                    item["unit_price"]
                )
            )

            conn.execute(
                """
                UPDATE products
                SET available_quantity = available_quantity - %s
                WHERE id = %s
                """,
                (item["item_quantity"], item["product_id"])
            )

        conn.execute(
            "DELETE FROM basket_items WHERE buyer_id = %s",
            (buyer_id,)
        )

    return {"message": "Purchase placed", "purchase": purchase}


# 9. Buyer purchase history — important hot-path endpoint
@app.get("/buyers/{buyer_id}/purchases")
def get_buyer_purchases(buyer_id: int):
    with get_connection("TEALBOX_DATABASE_URL") as conn:
        buyer = conn.execute(
            "SELECT id FROM buyers WHERE id = %s",
            (buyer_id,)
        ).fetchone()

        if not buyer:
            raise HTTPException(404, "Buyer not found")

        rows = conn.execute(
            """
            SELECT id, purchase_status, purchase_total, placed_at
            FROM purchases
            WHERE buyer_id = %s
            ORDER BY placed_at DESC
            LIMIT 50
            """,
            (buyer_id,)
        ).fetchall()

    return {"buyer_id": buyer_id, "purchases": rows}


# 10. API status
@app.get("/status")
def status():
    with get_connection("TEALBOX_DATABASE_URL") as conn:
        conn.execute("SELECT 1")

    return {
        "shop": "tealbox",
        "version": app.version,
        "status": "healthy"
    }

"""Product queries and reservation calculations shared by stock and delivery workflows."""

from dataclasses import replace

from .errors import ValidationError
from .models import Product

PRODUCT_FIELDS = "p.product_id,p.name,p.description,p.quantity,p.price,p.category,p.active,p.version"
PRODUCT_SELECT = (
    f"SELECT {PRODUCT_FIELDS},COALESCE((SELECT SUM(od.quantity) FROM order_details od "
    "JOIN deliveries d ON d.order_id=od.order_id "
    "WHERE od.product_id=p.product_id AND d.status='assigned'),0) AS reserved FROM products p "
)


def reserved_quantity(cursor, product_id: int, *, lock=False) -> int:
    cursor.execute(
        "SELECT od.quantity FROM order_details od JOIN deliveries d ON d.order_id=od.order_id "
        "WHERE od.product_id=%s AND d.status='assigned'" + (" FOR UPDATE" if lock else ""),
        (product_id,),
    )
    return sum(row["quantity"] for row in cursor.fetchall())


def product_for_update(cursor, product_id: int) -> Product:
    cursor.execute(f"SELECT {PRODUCT_FIELDS} FROM products p WHERE p.product_id=%s FOR UPDATE", (product_id,))
    row = cursor.fetchone()
    if row is None:
        raise ValidationError("This product no longer exists. Refresh the inventory.")
    return Product.from_row(row)


def with_reservations(cursor, product: Product) -> Product:
    return replace(product, reserved=reserved_quantity(cursor, product.product_id, lock=True))

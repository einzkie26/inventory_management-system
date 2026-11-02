"""Stock checkers record counts; only admins may apply a flagged correction."""

from .access import require_user
from .catalog import product_for_update, with_reservations
from .errors import ValidationError
from .models import quantity
from .roles import ADMIN, STOCK_ROLES


class StockService:
    def __init__(self, database):
        self.database = database

    def record_count(self, actor_id: int, product_id: int, counted, *, expected_version: int, notes="") -> int:
        counted = quantity(counted)
        notes = notes.strip()
        if len(notes) > 2000:
            raise ValidationError("Notes must be at most 2,000 characters.")
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, STOCK_ROLES)
            product = product_for_update(cursor, product_id)
            if not product.active:
                raise ValidationError("This product has been archived. Refresh the stock list.")
            if product.version != expected_version:
                raise ValidationError("Stock changed while you were counting. Refresh the product and record a new count.")
            difference = counted - product.quantity
            cursor.execute("UPDATE stock_checks SET status='superseded' WHERE product_id=%s AND status='flagged'", (product_id,))
            cursor.execute(
                "INSERT INTO stock_checks (product_id,product_name,expected_quantity,counted_quantity,difference,"
                "product_version,status,checked_by,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (product_id, product.name, product.quantity, counted, difference, product.version,
                 "flagged" if difference else "matched", actor_id, notes),
            )
            return cursor.lastrowid

    def list_checks(self, actor_id: int, *, flagged_only=False) -> list[dict]:
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, STOCK_ROLES)
            where = "WHERE s.status='flagged'" if flagged_only else ""
            cursor.execute(
                "SELECT s.*,u.username AS checked_by_name,a.username AS corrected_by_name "
                "FROM stock_checks s JOIN users u ON u.user_id=s.checked_by "
                "LEFT JOIN users a ON a.user_id=s.corrected_by "
                f"{where} ORDER BY s.checked_at DESC,s.check_id DESC"
            )
            return cursor.fetchall()

    def correct_count(self, actor_id: int, check_id: int):
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, {ADMIN})
            cursor.execute("SELECT product_id FROM stock_checks WHERE check_id=%s", (check_id,))
            identity = cursor.fetchone()
            if identity is None:
                raise ValidationError("Stock count not found. Refresh the list.")
            # All inventory workflows lock products before delivery or count records.
            product = with_reservations(cursor, product_for_update(cursor, identity["product_id"]))
            cursor.execute("SELECT * FROM stock_checks WHERE check_id=%s FOR UPDATE", (check_id,))
            check = cursor.fetchone()
            if check["status"] != "flagged":
                raise ValidationError("This stock count has already been reviewed or replaced by a newer count.")
            if product.version != check["product_version"] or product.quantity != check["expected_quantity"]:
                raise ValidationError("Stock changed after this count. Ask the stock checker to record a new count before correcting it.")
            if check["counted_quantity"] < product.reserved:
                raise ValidationError(
                    f"{product.reserved:,} units are reserved for assigned deliveries. "
                    "Cancel or change those deliveries before applying this correction."
                )
            cursor.execute("UPDATE products SET quantity=%s,version=version+1 WHERE product_id=%s", (check["counted_quantity"], product.product_id))
            cursor.execute(
                "INSERT INTO stock_movements (product_id,quantity_change,reason,created_by) VALUES (%s,%s,%s,%s)",
                (product.product_id, check["difference"], f"Stock count #{check_id} correction", actor_id),
            )
            cursor.execute(
                "UPDATE stock_checks SET status='corrected',corrected_by=%s,corrected_at=CURRENT_TIMESTAMP WHERE check_id=%s",
                (actor_id, check_id),
            )

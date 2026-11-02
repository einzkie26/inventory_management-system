"""Order and sales reporting for admins and inventory workers."""

from .access import require_user
from .errors import ValidationError
from .roles import INVENTORY_ROLES


class SalesService:
    def __init__(self, database):
        self.database = database

    def list_orders(self, actor_id: int) -> list[dict]:
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, INVENTORY_ROLES)
            cursor.execute(
                "SELECT o.order_id,o.user_id,o.username,o.recipient,o.destination,o.status,"
                "o.order_date,o.completed_at,o.total_price,"
                "COALESCE((SELECT SUM(od.quantity) FROM order_details od WHERE od.order_id=o.order_id),0) AS item_count "
                "FROM orders o ORDER BY o.order_date DESC,o.order_id DESC"
            )
            return cursor.fetchall()

    def order_detail(self, actor_id: int, order_id: int) -> dict:
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, INVENTORY_ROLES)
            cursor.execute(
                "SELECT order_id,user_id,username,recipient,destination,status,order_date,completed_at,total_price "
                "FROM orders WHERE order_id=%s", (order_id,),
            )
            order = cursor.fetchone()
            if order is None:
                raise ValidationError("This order is unavailable. Refresh the order list.")
            cursor.execute(
                "SELECT product_id,product_name,category,quantity,unit_price,price FROM order_details "
                "WHERE order_id=%s ORDER BY product_name,product_id", (order_id,),
            )
            order["items"] = cursor.fetchall()
            return order

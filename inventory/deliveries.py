"""Assigned product manifests, stock reservations, pickup, and delivery completion."""

from .access import require_user
from .catalog import product_for_update, with_reservations
from .errors import PermissionDenied, ValidationError
from .models import Manifest, money, quantity
from .roles import ADMIN, DELIVERY_ASSISTANT, INVENTORY_ROLES
from .validation import required_text

DELIVERY_SELECT = (
    "SELECT d.*,o.recipient,o.destination,o.order_date,"
    "a.username AS assistant_name,c.username AS created_by_name "
    "FROM deliveries d JOIN orders o ON o.order_id=d.order_id "
    "JOIN users a ON a.user_id=d.assigned_to JOIN users c ON c.user_id=d.created_by "
)


class DeliveryService:
    def __init__(self, database):
        self.database = database

    @staticmethod
    def _delivery(cursor, delivery_id: int, employee, *, lock=False):
        query = "SELECT d.* FROM deliveries d " if lock else DELIVERY_SELECT
        cursor.execute(query + "WHERE d.delivery_id=%s" + (" FOR UPDATE" if lock else ""), (delivery_id,))
        delivery = cursor.fetchone()
        if delivery is None or (employee.role == DELIVERY_ASSISTANT and delivery["assigned_to"] != employee.user_id):
            raise PermissionDenied("This delivery is unavailable or assigned to another employee.")
        return delivery

    @staticmethod
    def _event(cursor, delivery_id, status, actor_id, notes=""):
        cursor.execute(
            "INSERT INTO delivery_events (delivery_id,status,actor_id,notes) VALUES (%s,%s,%s,%s)",
            (delivery_id, status, actor_id, notes),
        )

    @staticmethod
    def _lock_products(cursor, order_id):
        cursor.execute("SELECT product_id,quantity FROM order_details WHERE order_id=%s ORDER BY product_id", (order_id,))
        items = cursor.fetchall()
        products = {row["product_id"]: product_for_update(cursor, row["product_id"]) for row in items}
        return items, {key: with_reservations(cursor, value) for key, value in products.items()}

    def create_delivery(self, actor_id: int, assistant_id: int, *, recipient: str, destination: str,
                        manifest: Manifest, notes="") -> int:
        recipient = required_text(recipient, "Recipient", 200)
        destination = required_text(destination, "Destination", 255)
        notes = notes.strip()
        if len(notes) > 2000:
            raise ValidationError("Delivery notes must be at most 2,000 characters.")
        requested = sorted(manifest.items, key=lambda item: item.product.product_id)
        if not requested:
            raise ValidationError("Add at least one product to the delivery.")
        with self.database.transaction() as cursor:
            actor = require_user(cursor, actor_id, INVENTORY_ROLES)
            require_user(cursor, assistant_id, {DELIVERY_ASSISTANT}, lock=True)
            # Lock every product in ID order before inspecting existing reservations.
            products = {item.product.product_id: product_for_update(cursor, item.product.product_id) for item in requested}
            total, validated = money("0"), []
            for item in requested:
                count = quantity(item.quantity, allow_zero=False)
                product = with_reservations(cursor, products[item.product.product_id])
                if not product.active or count > product.available:
                    raise ValidationError(f"Only {product.available:,} units of {product.name} are available for delivery. Refresh the products.")
                if product.price != item.product.price:
                    raise ValidationError(f"The price of {product.name} changed. Remove it and add it again before assigning the delivery.")
                line_total = money(product.price * count)
                total = money(total + line_total)
                validated.append((product, count, line_total))
            cursor.execute(
                "INSERT INTO orders (user_id,username,recipient,destination,status,total_price) "
                "VALUES (%s,%s,%s,%s,'pending_delivery',%s)",
                (actor_id, actor.username, recipient, destination, total),
            )
            order_id = cursor.lastrowid
            for product, count, line_total in validated:
                cursor.execute(
                    "INSERT INTO order_details (order_id,product_id,product_name,category,quantity,unit_price,price) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (order_id, product.product_id, product.name, product.category, count, product.price, line_total),
                )
                cursor.execute("UPDATE products SET version=version+1 WHERE product_id=%s", (product.product_id,))
            cursor.execute(
                "INSERT INTO deliveries (order_id,assigned_to,created_by,notes) VALUES (%s,%s,%s,%s)",
                (order_id, assistant_id, actor_id, notes),
            )
            delivery_id = cursor.lastrowid
            self._event(cursor, delivery_id, "assigned", actor_id, "Delivery assigned")
            return delivery_id

    def list_deliveries(self, actor_id: int, status=None) -> list[dict]:
        if status not in {None, "assigned", "in_transit", "delivered", "cancelled"}:
            raise ValidationError("Select a valid delivery status.")
        with self.database.transaction() as cursor:
            employee = require_user(cursor, actor_id)
            clauses, params = [], []
            if employee.role == DELIVERY_ASSISTANT:
                clauses.append("d.assigned_to=%s")
                params.append(actor_id)
            if status:
                clauses.append("d.status=%s")
                params.append(status)
            where = "WHERE " + " AND ".join(clauses) if clauses else ""
            cursor.execute(DELIVERY_SELECT + where + " ORDER BY d.assigned_at DESC,d.delivery_id DESC", tuple(params))
            rows = cursor.fetchall()
            for row in rows:
                cursor.execute("SELECT product_name,quantity FROM order_details WHERE order_id=%s ORDER BY product_name", (row["order_id"],))
                items = cursor.fetchall()
                row["products"] = ", ".join(f"{item['product_name']} × {item['quantity']}" for item in items)
                row["units"] = sum(item["quantity"] for item in items)
            return rows

    def delivery_detail(self, actor_id: int, delivery_id: int) -> dict:
        with self.database.transaction() as cursor:
            employee = require_user(cursor, actor_id)
            delivery = self._delivery(cursor, delivery_id, employee)
            cursor.execute(
                "SELECT product_id,product_name,category,quantity FROM order_details "
                "WHERE order_id=%s ORDER BY product_name,product_id", (delivery["order_id"],),
            )
            delivery["items"] = cursor.fetchall()
            cursor.execute(
                "SELECT e.status,e.notes,e.created_at,u.username AS actor_name FROM delivery_events e "
                "JOIN users u ON u.user_id=e.actor_id WHERE e.delivery_id=%s ORDER BY e.event_id", (delivery_id,),
            )
            delivery["events"] = cursor.fetchall()
            return delivery

    def mark_picked_up(self, actor_id: int, delivery_id: int):
        with self.database.transaction() as cursor:
            employee = require_user(cursor, actor_id, {ADMIN, DELIVERY_ASSISTANT})
            initial = self._delivery(cursor, delivery_id, employee)
            items, products = self._lock_products(cursor, initial["order_id"])
            delivery = self._delivery(cursor, delivery_id, employee, lock=True)
            if delivery["status"] != "assigned":
                raise ValidationError("Only an assigned delivery can be picked up. Refresh the list.")
            for item in items:
                product = products[item["product_id"]]
                if not product.active or product.quantity < product.reserved:
                    raise ValidationError(f"Stock for {product.name} needs an admin review before pickup.")
                cursor.execute(
                    "UPDATE products SET quantity=quantity-%s,version=version+1 WHERE product_id=%s AND quantity>=%s",
                    (item["quantity"], product.product_id, item["quantity"]),
                )
                if cursor.rowcount != 1:
                    raise ValidationError(f"There is not enough stock of {product.name} for pickup.")
                cursor.execute(
                    "INSERT INTO stock_movements (product_id,quantity_change,reason,order_id,created_by) VALUES (%s,%s,%s,%s,%s)",
                    (product.product_id, -item["quantity"], f"Delivery #{delivery_id} pickup", delivery["order_id"], actor_id),
                )
            cursor.execute("UPDATE deliveries SET status='in_transit',picked_up_at=CURRENT_TIMESTAMP WHERE delivery_id=%s", (delivery_id,))
            cursor.execute("UPDATE orders SET status='in_transit' WHERE order_id=%s", (delivery["order_id"],))
            self._event(cursor, delivery_id, "in_transit", actor_id, "Products picked up")

    def mark_delivered(self, actor_id: int, delivery_id: int):
        with self.database.transaction() as cursor:
            employee = require_user(cursor, actor_id, {ADMIN, DELIVERY_ASSISTANT})
            delivery = self._delivery(cursor, delivery_id, employee, lock=True)
            if delivery["status"] != "in_transit":
                raise ValidationError("Pick up this delivery before marking it delivered.")
            cursor.execute("UPDATE deliveries SET status='delivered',delivered_at=CURRENT_TIMESTAMP WHERE delivery_id=%s", (delivery_id,))
            cursor.execute("UPDATE orders SET status='completed',completed_at=CURRENT_TIMESTAMP WHERE order_id=%s", (delivery["order_id"],))
            self._event(cursor, delivery_id, "delivered", actor_id, "Delivery completed")

    def cancel_delivery(self, actor_id: int, delivery_id: int):
        with self.database.transaction() as cursor:
            employee = require_user(cursor, actor_id, INVENTORY_ROLES)
            initial = self._delivery(cursor, delivery_id, employee)
            items, _products = self._lock_products(cursor, initial["order_id"])
            delivery = self._delivery(cursor, delivery_id, employee, lock=True)
            if delivery["status"] != "assigned":
                raise ValidationError("Only deliveries awaiting pickup can be cancelled.")
            cursor.execute("UPDATE deliveries SET status='cancelled',cancelled_at=CURRENT_TIMESTAMP WHERE delivery_id=%s", (delivery_id,))
            cursor.execute("UPDATE orders SET status='cancelled' WHERE order_id=%s", (delivery["order_id"],))
            for item in items:
                cursor.execute("UPDATE products SET version=version+1 WHERE product_id=%s", (item["product_id"],))
            self._event(cursor, delivery_id, "cancelled", actor_id, "Delivery cancelled; reservations released")

    def reassign_delivery(self, actor_id: int, delivery_id: int, assistant_id: int):
        with self.database.transaction() as cursor:
            employee = require_user(cursor, actor_id, INVENTORY_ROLES)
            assistant = require_user(cursor, assistant_id, {DELIVERY_ASSISTANT}, lock=True)
            initial = self._delivery(cursor, delivery_id, employee)
            self._lock_products(cursor, initial["order_id"])
            delivery = self._delivery(cursor, delivery_id, employee, lock=True)
            if delivery["status"] != "assigned":
                raise ValidationError("Only deliveries awaiting pickup can be reassigned.")
            cursor.execute("UPDATE deliveries SET assigned_to=%s WHERE delivery_id=%s", (assistant_id, delivery_id))
            self._event(cursor, delivery_id, "assigned", actor_id, f"Reassigned to {assistant.username}")

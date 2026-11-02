"""Authentication, product management, and the employee workflow services."""

from .access import USER_FIELDS, require_user
from .catalog import PRODUCT_SELECT, product_for_update, with_reservations
from .db import Database
from .employees import EmployeeService
from .errors import AuthenticationError, PermissionDenied, ValidationError
from .models import Product, User, money, quantity
from .roles import ADMIN, ALL_ROLES, INVENTORY_ROLES, INVENTORY_WORKER, STOCK_CHECKER
from .security import hash_password, verify_password
from .validation import account_credentials, required_text


class InventoryService:
    def __init__(self, database: Database):
        from .deliveries import DeliveryService
        from .sales import SalesService
        from .stock import StockService

        self.database = database
        self.employees = EmployeeService(database)
        self.stock = StockService(database)
        self.deliveries = DeliveryService(database)
        self.sales = SalesService(database)

    def needs_setup(self) -> bool:
        with self.database.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM users WHERE role='admin' AND active=1")
            return cursor.fetchone()["count"] == 0

    def setup_admin(self, username: str, email: str, password: str) -> User:
        values = account_credentials(username, email, password)
        with self.database.transaction() as cursor:
            cursor.execute("SELECT state_id FROM app_state WHERE state_id=1 FOR UPDATE")
            cursor.fetchone()
            cursor.execute("SELECT user_id FROM users WHERE role='admin' LIMIT 1 FOR UPDATE")
            if cursor.fetchone():
                raise PermissionDenied("An admin account already exists. Contact your administrator to restore access.")
            cursor.execute("INSERT INTO users (username,email,password,role) VALUES (%s,%s,%s,'admin')", values)
            return require_user(cursor, cursor.lastrowid)

    def authenticate(self, login: str, password: str) -> User:
        login = login.strip()
        if not login or not password or len(password) > 128:
            raise AuthenticationError("Enter your username or email and password.")
        with self.database.transaction() as cursor:
            cursor.execute(f"SELECT {USER_FIELDS},password FROM users WHERE username=%s OR email=%s LIMIT 1", (login, login))
            row = cursor.fetchone()
        if row is None:
            hash_password(password)
            raise AuthenticationError("Invalid username/email or password.")
        valid, upgrade = verify_password(password, row["password"])
        if not valid:
            raise AuthenticationError("Invalid username/email or password.")
        if not row["active"] or row["role"] not in ALL_ROLES:
            raise AuthenticationError("Your employee account is unavailable. Contact an admin.")
        if upgrade:
            replacement = hash_password(password)
            with self.database.transaction() as cursor:
                cursor.execute("UPDATE users SET password=%s WHERE user_id=%s AND password=%s", (replacement, row["user_id"], row["password"]))
        return User.from_row(row)

    def get_user(self, actor_id: int) -> User:
        with self.database.transaction() as cursor:
            return require_user(cursor, actor_id)

    def list_products(self, actor_id: int, search="", *, include_archived=False) -> list[Product]:
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, INVENTORY_ROLES | {STOCK_CHECKER})
            filters, params = [], []
            if not include_archived:
                filters.append("p.active=1")
            if search.strip():
                filters.append("(p.name LIKE %s OR p.category LIKE %s OR p.description LIKE %s)")
                params.extend(["%" + search.strip() + "%"] * 3)
            where = " WHERE " + " AND ".join(filters) if filters else ""
            cursor.execute(PRODUCT_SELECT + where + " ORDER BY p.active DESC,p.name,p.product_id", tuple(params))
            return [Product.from_row(row) for row in cursor.fetchall()]

    def save_product(self, actor_id: int, *, name: str, description: str, count, price, category: str,
                     product_id=None, expected_version=None) -> int:
        name = required_text(name, "Product name", 200)
        category = required_text(category, "Category", 80)
        description = description.strip()
        if len(description) > 2000:
            raise ValidationError("Description must be at most 2,000 characters.")
        values = name, description, quantity(count), money(price), category
        with self.database.transaction() as cursor:
            employee = require_user(cursor, actor_id, INVENTORY_ROLES)
            if product_id is None:
                cursor.execute("INSERT INTO products (name,description,quantity,price,category) VALUES (%s,%s,%s,%s,%s)", values)
                product_id, difference = cursor.lastrowid, values[2]
            else:
                previous = with_reservations(cursor, product_for_update(cursor, product_id))
                if expected_version is None or previous.version != expected_version:
                    raise ValidationError("This product changed while you were editing it. Close the editor, refresh, and try again.")
                if values[2] < previous.reserved:
                    raise ValidationError(f"{previous.reserved:,} units are reserved for assigned deliveries. Cancel or change those deliveries first.")
                if employee.role == INVENTORY_WORKER and values[2] < previous.quantity:
                    raise PermissionDenied("Only an admin can reduce stock. Stock checkers flag differences for an admin to correct.")
                difference = values[2] - previous.quantity
                cursor.execute(
                    "UPDATE products SET name=%s,description=%s,quantity=%s,price=%s,category=%s,version=version+1 WHERE product_id=%s",
                    values + (product_id,),
                )
            if difference:
                cursor.execute(
                    "INSERT INTO stock_movements (product_id,quantity_change,reason,created_by) VALUES (%s,%s,'Inventory adjustment',%s)",
                    (product_id, difference, actor_id),
                )
            return product_id

    def set_product_active(self, actor_id: int, product_id: int, active: bool):
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, INVENTORY_ROLES)
            product = with_reservations(cursor, product_for_update(cursor, product_id))
            if not active and product.reserved:
                raise ValidationError("This product is reserved for an assigned delivery. Cancel the delivery before archiving it.")
            cursor.execute("UPDATE products SET active=%s,version=version+1 WHERE product_id=%s", (bool(active), product_id))

    def dashboard(self, actor_id: int) -> dict:
        with self.database.transaction() as cursor:
            viewer = require_user(cursor, actor_id, INVENTORY_ROLES | {STOCK_CHECKER})
            cursor.execute("SELECT COUNT(*) AS active_products,COALESCE(SUM(quantity),0) AS total_units,COALESCE(SUM(quantity<=5),0) AS low_stock FROM products WHERE active=1")
            stats = cursor.fetchone()
            cursor.execute("SELECT COALESCE(SUM(od.quantity),0) AS reserved_units FROM order_details od JOIN deliveries d ON d.order_id=od.order_id WHERE d.status='assigned'")
            stats.update(cursor.fetchone())
            stats["available_units"] = stats["total_units"] - stats["reserved_units"]
            if viewer.role in INVENTORY_ROLES:
                cursor.execute("SELECT COUNT(*) AS orders_count,COALESCE(SUM(CASE WHEN status='completed' THEN total_price ELSE 0 END),0) AS total_sales FROM orders")
                stats.update(cursor.fetchone())
            cursor.execute("SELECT COUNT(*) AS employee_count FROM users WHERE active=1")
            stats.update(cursor.fetchone())
            cursor.execute("SELECT COUNT(*) AS flagged_checks FROM stock_checks WHERE status='flagged'")
            stats.update(cursor.fetchone())
            return stats

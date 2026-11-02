"""Role permissions, stock flags, delivery transactions, and sales integration."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
import threading

from inventory.backup import backup_database, quote_identifier
from inventory.db import Database
from inventory.deliveries import DeliveryService
from inventory.errors import AuthenticationError, DatabaseError, PermissionDenied, ValidationError
from inventory.models import Manifest
from inventory.receipts import export_manifest, export_receipt
from inventory.roles import ADMIN, DELIVERY_ASSISTANT, INVENTORY_WORKER, STOCK_CHECKER
from inventory.services import InventoryService

from .mysql_support import MySQLTestCase


class ServiceTests(MySQLTestCase):
    def setUp(self):
        super().setUp()
        self.db.initialize()
        self.service = InventoryService(self.db)
        self.admin = self.service.authenticate("admin", "Admin1234!")
        self.worker = self.employee("worker", INVENTORY_WORKER)
        self.checker = self.employee("checker", STOCK_CHECKER)
        self.driver = self.employee("driver", DELIVERY_ASSISTANT)

    def employee(self, name, role):
        return self.service.employees.create_employee(self.admin.user_id, name, name + "@example.org", "Employee123!", role)

    def product(self, *, name="Notebook", stock=10, price="1.25"):
        product_id = self.service.save_product(self.worker.user_id, name=name, description="A useful item", count=stock, price=price, category="Stationery")
        return next(p for p in self.service.list_products(self.worker.user_id) if p.product_id == product_id)

    def manifest(self, product, count=2):
        manifest = Manifest()
        manifest.add(product, count)
        return manifest

    def assign(self, product=None, count=2, driver=None):
        product = product if product is not None else self.product()
        return self.service.deliveries.create_delivery(self.worker.user_id, (driver or self.driver).user_id, recipient="Store A", destination="12 Warehouse Road", manifest=self.manifest(product, count), notes="Call on arrival")

    def fresh_product(self, product_id):
        return next(p for p in self.service.list_products(self.admin.user_id, include_archived=True) if p.product_id == product_id)

    def test_admin_creates_employees_with_all_four_roles(self):
        extra_admin = self.employee("secondadmin", ADMIN)
        employees = self.service.employees.list_employees(self.admin.user_id)
        self.assertEqual({u.role for u in employees}, {ADMIN, INVENTORY_WORKER, STOCK_CHECKER, DELIVERY_ASSISTANT})
        self.assertEqual(len(employees), 5)
        self.assertEqual(self.service.get_user(extra_admin.user_id).role, ADMIN)
        with self.assertRaises(ValidationError):
            self.employee("unsupported", "customer")

    def test_authentication_uniqueness_and_disabled_accounts(self):
        self.assertEqual(self.service.authenticate("WORKER@EXAMPLE.ORG", "Employee123!").user_id, self.worker.user_id)
        with self.assertRaises(AuthenticationError):
            self.service.authenticate("' OR '1'='1", "Employee123!")
        with self.assertRaises(AuthenticationError):
            self.service.authenticate("worker", "incorrect")
        with self.assertRaises(ValidationError):
            self.employee("WORKER", STOCK_CHECKER)
        self.service.employees.update_employee(self.admin.user_id, self.worker.user_id, role=INVENTORY_WORKER, active=False)
        with self.assertRaises(AuthenticationError):
            self.service.authenticate("worker", "Employee123!")
        with self.assertRaises(AuthenticationError):
            self.service.list_products(self.worker.user_id)
        self.assertTrue(self.scalar("SELECT password FROM users WHERE user_id=%s", (self.worker.user_id,)).startswith("pbkdf2_sha256$"))

    def test_permissions_are_enforced_below_the_interface(self):
        product = self.product()
        operations = [
            lambda: self.service.employees.list_employees(self.worker.user_id),
            lambda: self.service.employees.create_employee(self.worker.user_id, "rogueadmin", "rogue@example.org", "Password123!", ADMIN),
            lambda: self.service.save_product(self.checker.user_id, name="X", description="", count=1, price="1", category="X"),
            lambda: self.service.set_product_active(self.checker.user_id, product.product_id, False),
            lambda: self.service.list_products(self.driver.user_id),
            lambda: self.service.sales.list_orders(self.checker.user_id),
            lambda: self.service.sales.list_orders(self.driver.user_id),
            lambda: self.service.stock.list_checks(self.worker.user_id),
            lambda: self.service.stock.record_count(self.worker.user_id, product.product_id, 1, expected_version=product.version),
            lambda: self.service.deliveries.create_delivery(self.checker.user_id, self.driver.user_id, recipient="X", destination="X", manifest=self.manifest(product)),
        ]
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaises(PermissionDenied):
                operation()

    def test_last_admin_and_first_run_setup_are_protected(self):
        self.assertFalse(self.service.needs_setup())
        with self.assertRaises(PermissionDenied):
            self.service.setup_admin("rogueadmin", "rogue@example.org", "Password123!")
        with self.assertRaises(ValidationError):
            self.service.employees.update_employee(self.admin.user_id, self.admin.user_id, role=INVENTORY_WORKER, active=True)
        with self.assertRaises(ValidationError):
            self.service.employees.update_employee(self.admin.user_id, self.admin.user_id, role=ADMIN, active=False)
        self.employee("secondadmin", ADMIN)
        self.service.employees.update_employee(self.admin.user_id, self.admin.user_id, role=INVENTORY_WORKER, active=True)
        with self.assertRaises(PermissionDenied):
            self.service.employees.list_employees(self.admin.user_id)

    def test_assignment_reserves_products_and_pickup_deducts_exactly_once(self):
        product = self.product(price="0.10")
        manifest = self.manifest(product, 2)
        manifest.add(product, 3)
        delivery_id = self.service.deliveries.create_delivery(self.worker.user_id, self.driver.user_id, recipient="Store A", destination="Warehouse Road", manifest=manifest)
        fresh = self.fresh_product(product.product_id)
        self.assertEqual((fresh.quantity, fresh.reserved, fresh.available), (10, 5, 5))
        self.assertEqual(self.service.dashboard(self.worker.user_id)["total_sales"], Decimal("0.00"))
        delivery = self.service.deliveries.delivery_detail(self.driver.user_id, delivery_id)
        self.assertEqual(delivery["items"][0]["quantity"], 5)
        self.assertEqual(len(delivery["items"]), 1)
        self.assertNotIn("total_price", delivery)
        self.assertNotIn("unit_price", delivery["items"][0])
        self.service.deliveries.mark_picked_up(self.driver.user_id, delivery_id)
        fresh = self.fresh_product(product.product_id)
        self.assertEqual((fresh.quantity, fresh.reserved, fresh.available), (5, 0, 5))
        with self.assertRaises(ValidationError):
            self.service.deliveries.mark_picked_up(self.driver.user_id, delivery_id)
        self.service.deliveries.mark_delivered(self.driver.user_id, delivery_id)
        self.assertEqual(self.fresh_product(product.product_id).quantity, 5)
        self.assertEqual(self.service.dashboard(self.worker.user_id)["total_sales"], Decimal("0.50"))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM stock_movements WHERE order_id IS NOT NULL"), 1)
        self.assertEqual([e["status"] for e in self.service.deliveries.delivery_detail(self.driver.user_id, delivery_id)["events"]], ["assigned", "in_transit", "delivered"])

    def test_assistants_only_see_their_own_manifests(self):
        delivery_id = self.assign()
        other = self.employee("otherdriver", DELIVERY_ASSISTANT)
        self.assertEqual(self.service.deliveries.list_deliveries(other.user_id), [])
        for operation in (
            lambda: self.service.deliveries.delivery_detail(other.user_id, delivery_id),
            lambda: self.service.deliveries.mark_picked_up(other.user_id, delivery_id),
            lambda: self.service.deliveries.mark_delivered(other.user_id, delivery_id),
            lambda: self.service.deliveries.cancel_delivery(self.driver.user_id, delivery_id),
            lambda: self.service.deliveries.mark_picked_up(self.worker.user_id, delivery_id),
        ):
            with self.subTest(operation=operation), self.assertRaises(PermissionDenied):
                operation()

    def test_delivery_state_transitions_cannot_skip_pickup_or_repeat(self):
        delivery_id = self.assign()
        with self.assertRaises(ValidationError):
            self.service.deliveries.mark_delivered(self.driver.user_id, delivery_id)
        self.service.deliveries.mark_picked_up(self.driver.user_id, delivery_id)
        with self.assertRaises(ValidationError):
            self.service.deliveries.cancel_delivery(self.admin.user_id, delivery_id)
        self.service.deliveries.mark_delivered(self.driver.user_id, delivery_id)
        with self.assertRaises(ValidationError):
            self.service.deliveries.mark_delivered(self.driver.user_id, delivery_id)

    def test_concurrent_assignments_cannot_over_reserve(self):
        product = self.product(stock=1)
        other = self.employee("otherdriver", DELIVERY_ASSISTANT)
        barrier = threading.Barrier(2)

        def assign(driver):
            barrier.wait(timeout=5)
            try:
                return self.assign(product, 1, driver)
            except ValidationError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(assign, (self.driver, other)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 1)
        fresh = self.fresh_product(product.product_id)
        self.assertEqual((fresh.quantity, fresh.reserved, fresh.available), (1, 1, 0))

    def test_concurrent_pickups_do_not_deduct_stock_twice(self):
        product = self.product()
        delivery_id = self.assign(product, 3)
        barrier = threading.Barrier(2)

        def pick_up(actor):
            barrier.wait(timeout=5)
            try:
                self.service.deliveries.mark_picked_up(actor, delivery_id)
                return True
            except ValidationError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(pick_up, (self.driver.user_id, self.admin.user_id)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(self.fresh_product(product.product_id).quantity, 7)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM stock_movements WHERE order_id IS NOT NULL"), 1)

    def test_stock_checker_flags_differences_without_editing_stock(self):
        product = self.product()
        check_id = self.service.stock.record_count(self.checker.user_id, product.product_id, 8, expected_version=product.version, notes="Two items missing")
        self.assertEqual(self.fresh_product(product.product_id).quantity, 10)
        check = self.service.stock.list_checks(self.admin.user_id)[0]
        self.assertEqual((check["difference"], check["status"]), (-2, "flagged"))
        with self.assertRaises(PermissionDenied):
            self.service.stock.correct_count(self.checker.user_id, check_id)
        self.service.stock.correct_count(self.admin.user_id, check_id)
        self.assertEqual(self.fresh_product(product.product_id).quantity, 8)
        self.assertEqual(self.service.stock.list_checks(self.checker.user_id)[0]["status"], "corrected")
        self.assertEqual(self.scalar("SELECT quantity_change FROM stock_movements WHERE reason LIKE 'Stock count%'"), -2)

    def test_stale_counts_and_corrections_do_not_overwrite_new_stock(self):
        product = self.product()
        check_id = self.service.stock.record_count(self.checker.user_id, product.product_id, 8, expected_version=product.version)
        self.service.save_product(self.worker.user_id, name=product.name, description="", count=12, price=product.price, category=product.category, product_id=product.product_id, expected_version=product.version)
        with self.assertRaises(ValidationError):
            self.service.stock.correct_count(self.admin.user_id, check_id)
        with self.assertRaises(ValidationError):
            self.service.stock.record_count(self.checker.user_id, product.product_id, 8, expected_version=product.version)
        fresh = self.fresh_product(product.product_id)
        self.service.stock.record_count(self.checker.user_id, product.product_id, 12, expected_version=fresh.version)
        self.assertEqual(self.service.stock.list_checks(self.admin.user_id)[1]["status"], "superseded")
        self.assertEqual(self.fresh_product(product.product_id).quantity, 12)

    def test_reserved_stock_cannot_be_corrected_away_or_archived(self):
        product = self.product()
        self.assign(product, 7)
        fresh = self.fresh_product(product.product_id)
        check_id = self.service.stock.record_count(self.checker.user_id, product.product_id, 3, expected_version=fresh.version)
        with self.assertRaises(ValidationError):
            self.service.stock.correct_count(self.admin.user_id, check_id)
        with self.assertRaises(ValidationError):
            self.service.set_product_active(self.admin.user_id, product.product_id, False)
        with self.assertRaises(ValidationError):
            self.service.save_product(self.admin.user_id, name=product.name, description="", count=3, price=product.price, category=product.category, product_id=product.product_id, expected_version=fresh.version)
        self.assertEqual(self.fresh_product(product.product_id).quantity, 10)

    def test_cancel_releases_reservations_and_reassignment_changes_visibility(self):
        product = self.product()
        delivery_id = self.assign(product)
        other = self.employee("otherdriver", DELIVERY_ASSISTANT)
        with self.assertRaises(ValidationError):
            self.service.employees.update_employee(self.admin.user_id, self.driver.user_id, role=DELIVERY_ASSISTANT, active=False)
        self.service.deliveries.reassign_delivery(self.admin.user_id, delivery_id, other.user_id)
        self.assertEqual(self.service.deliveries.list_deliveries(self.driver.user_id), [])
        self.assertEqual(len(self.service.deliveries.list_deliveries(other.user_id)), 1)
        self.service.deliveries.cancel_delivery(self.worker.user_id, delivery_id)
        fresh = self.fresh_product(product.product_id)
        self.assertEqual((fresh.quantity, fresh.reserved, fresh.available), (10, 0, 10))
        self.assertEqual(self.service.sales.list_orders(self.worker.user_id)[0]["status"], "cancelled")
        self.service.employees.update_employee(self.admin.user_id, other.user_id, role=DELIVERY_ASSISTANT, active=False)

    def test_product_renames_keep_the_assigned_manifest_and_sale_snapshots(self):
        product = self.product()
        delivery_id = self.assign(product)
        fresh = self.fresh_product(product.product_id)
        self.service.save_product(self.worker.user_id, name="Renamed item", description="", count=fresh.quantity, price="99", category="New category", product_id=product.product_id, expected_version=fresh.version)
        detail = self.service.deliveries.delivery_detail(self.driver.user_id, delivery_id)
        self.assertEqual(detail["items"][0]["product_name"], "Notebook")
        self.assertEqual(detail["items"][0]["category"], "Stationery")
        order = self.service.sales.order_detail(self.worker.user_id, detail["order_id"])
        self.assertEqual(order["items"][0]["unit_price"], Decimal("1.25"))

    def test_inventory_workers_can_restock_but_cannot_reduce_stock(self):
        product = self.product()
        with self.assertRaises(PermissionDenied):
            self.service.save_product(self.worker.user_id, name=product.name, description="", count=5, price=product.price, category=product.category, product_id=product.product_id, expected_version=product.version)
        self.service.save_product(self.worker.user_id, name=product.name, description="", count=15, price=product.price, category=product.category, product_id=product.product_id, expected_version=product.version)
        self.assertEqual(self.fresh_product(product.product_id).quantity, 15)

    def test_wrong_roles_and_inactive_assistants_cannot_receive_deliveries(self):
        product = self.product()
        with self.assertRaises(PermissionDenied):
            self.service.deliveries.create_delivery(self.worker.user_id, self.checker.user_id, recipient="Store", destination="Road", manifest=self.manifest(product))
        self.service.employees.update_employee(self.admin.user_id, self.driver.user_id, role=DELIVERY_ASSISTANT, active=False)
        with self.assertRaises(AuthenticationError):
            self.assign(product)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 0)

    def failing_deliveries(self, sql_prefix):
        class FailingCursor:
            def __init__(self, cursor):
                self.cursor = cursor

            def __getattr__(self, name):
                return getattr(self.cursor, name)

            def execute(self, query, params=()):
                if query.startswith(sql_prefix):
                    raise RuntimeError("Simulated failure after partial writes")
                return self.cursor.execute(query, params)

        class FailingDatabase:
            @contextmanager
            def transaction(inner_self):
                with self.db.transaction() as cursor:
                    yield FailingCursor(cursor)

        return DeliveryService(FailingDatabase())

    def test_assignment_failure_rolls_back_order_lines_and_reservations(self):
        product = self.product()
        service = self.failing_deliveries("INSERT INTO deliveries")
        with self.assertRaises(RuntimeError):
            service.create_delivery(self.worker.user_id, self.driver.user_id, recipient="Store", destination="Road", manifest=self.manifest(product))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM order_details"), 0)
        fresh = self.fresh_product(product.product_id)
        self.assertEqual((fresh.version, fresh.reserved, fresh.quantity), (product.version, 0, 10))

    def test_pickup_failure_rolls_back_stock_status_timestamps_and_audit(self):
        product = self.product()
        delivery_id = self.assign(product)
        with self.assertRaises(RuntimeError):
            self.failing_deliveries("INSERT INTO delivery_events").mark_picked_up(self.driver.user_id, delivery_id)
        fresh = self.fresh_product(product.product_id)
        self.assertEqual((fresh.quantity, fresh.reserved), (10, 2))
        delivery = self.service.deliveries.delivery_detail(self.driver.user_id, delivery_id)
        self.assertEqual(delivery["status"], "assigned")
        self.assertIsNone(delivery["picked_up_at"])
        self.assertEqual(len(delivery["events"]), 1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM stock_movements WHERE order_id IS NOT NULL"), 0)
        self.assertEqual(self.service.sales.list_orders(self.worker.user_id)[0]["status"], "pending_delivery")

    def test_database_constraints_limit_roles_and_negative_stock(self):
        product = self.product()
        for query, params in (
            ("UPDATE products SET quantity=-1 WHERE product_id=%s", (product.product_id,)),
            ("UPDATE users SET role='customer' WHERE user_id=%s", (self.worker.user_id,)),
        ):
            with self.subTest(query=query), self.assertRaises(DatabaseError):
                with self.db.transaction() as cursor:
                    cursor.execute(query, params)

    def test_export_failures_do_not_undo_saved_deliveries(self):
        delivery_id = self.assign()
        detail = self.service.deliveries.delivery_detail(self.driver.user_id, delivery_id)
        blocked = self.db.settings.receipt_dir
        blocked.write_text("not a directory", encoding="utf-8")
        with self.assertRaises(OSError):
            export_manifest(detail, blocked)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM deliveries"), 1)
        blocked.unlink()
        path = export_manifest(detail, blocked)
        self.assertIn("Notebook | Stationery | Quantity: 2", path.read_text(encoding="utf-8"))
        order = self.service.sales.order_detail(self.worker.user_id, detail["order_id"])
        self.assertIn("TOTAL: $2.50", export_receipt(order, blocked).read_text(encoding="utf-8"))

    def test_backup_round_trip_preserves_employees_delivery_and_reservations(self):
        product = self.product(name="Crème O'Reilly\\box; 测试")
        delivery_id = self.assign(product)
        path = backup_database(self.db)
        restored_schema = self.schema[:-1] + ("0" if self.schema[-1] != "0" else "1")
        restore = Database(replace(self.db.settings, database=restored_schema))
        connection = restore.connect(server_only=True)
        cursor = connection.cursor()
        try:
            cursor.execute(f"CREATE DATABASE {quote_identifier(restored_schema)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            self.addCleanup(self.drop_test_schema, restored_schema)
        finally:
            cursor.close()
            connection.close()
        connection = restore.connect()
        cursor = connection.cursor()
        try:
            for statement in path.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    cursor.execute(statement)
            connection.commit()
        finally:
            cursor.close()
            connection.close()
        service = InventoryService(restore)
        self.assertEqual(service.list_products(self.admin.user_id)[0].name, product.name)
        self.assertEqual(service.list_products(self.admin.user_id)[0].reserved, 2)
        self.assertEqual(service.get_user(self.driver.user_id).role, DELIVERY_ASSISTANT)
        self.assertEqual(service.deliveries.delivery_detail(self.driver.user_id, delivery_id)["destination"], "12 Warehouse Road")
        restore.initialize()

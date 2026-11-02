"""End-to-end desktop coverage of all four employee roles."""

from decimal import Decimal
import os
from pathlib import Path
import time
import tkinter as tk
from unittest.mock import patch

from inventory.app import InventoryApp
from inventory.errors import DatabaseError
from inventory.roles import ADMIN, DELIVERY_ASSISTANT, INVENTORY_WORKER, ROLE_LABELS, STOCK_CHECKER
from inventory.ui.auth import AuthView
from inventory.ui.delivery_dialogs import AssignDeliveryDialog, DeliveryManifestDialog
from inventory.ui.dialogs import EmployeeDialog, ProductDialog, StockCountDialog, StockReviewDialog
from inventory.ui.employees import EmployeesView
from inventory.ui.shell import Shell

from .mysql_support import MySQLTestCase


class DesktopWorkflowTests(MySQLTestCase):
    def setUp(self):
        if os.getenv("INVENTORY_TEST_GUI") != "1":
            self.skipTest("Set INVENTORY_TEST_GUI=1 to run the desktop workflow test.")
        super().setUp()
        self.messages = []
        for name in ("showerror", "showinfo"):
            mocked = patch(f"tkinter.messagebox.{name}", side_effect=lambda title, message, **_kwargs: self.messages.append((title, message)))
            mocked.start()
            self.addCleanup(mocked.stop)
        confirmations = patch("tkinter.messagebox.askyesno", return_value=True)
        confirmations.start()
        self.addCleanup(confirmations.stop)
        self.app = InventoryApp(database=self.db)
        self.addCleanup(self.app.close)
        self.wait_idle()

    def wait_idle(self):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            self.app.root.update()
            if not self.app.busy:
                self.app.root.update()
                if not self.app.busy:
                    return
            time.sleep(0.01)
        self.fail(f"UI task did not complete: {self.messages}")

    def modal(self, cls):
        found = [window for window in self.app.root.winfo_children() if isinstance(window, cls)]
        self.assertEqual(len(found), 1, f"Expected one {cls.__name__}; messages: {self.messages}")
        return found[0]

    def descendants(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self.descendants(child)

    def login(self, username, password="Employee123!"):
        self.assertIsInstance(self.app.view, AuthView)
        self.app.view.username.set(username)
        self.app.view.password.set(password)
        self.app.view.submit()
        self.wait_idle()
        self.assertIsInstance(self.app.view, Shell, self.messages)

    def assert_visible_actions(self, widget=None):
        if widget is None or isinstance(widget, tk.Toplevel):
            self.app.root.update()
        else:
            self.app.root.update_idletasks()
        widget = widget if widget is not None else self.app.root
        for child in widget.winfo_children():
            if isinstance(child, tk.Toplevel):
                continue
            if child.winfo_manager() and child.winfo_class() in {"TButton", "TEntry", "TSpinbox", "TCheckbutton", "TCombobox"}:
                self.assertTrue(child.winfo_ismapped(), f"Action is hidden: {child}")
                parent = child.master
                self.assertGreater(child.winfo_width(), 8, str(child))
                self.assertGreaterEqual(child.winfo_x(), -2, str(child))
                self.assertLessEqual(child.winfo_x() + child.winfo_width(), parent.winfo_width() + 3, str(child))
                self.assertLessEqual(child.winfo_y() + child.winfo_height(), parent.winfo_height() + 3, str(child))
            self.assert_visible_actions(child)

    def snapshot(self, name, window=None):
        directory = os.getenv("INVENTORY_TEST_SCREENSHOTS")
        if not directory:
            return
        try:
            from PIL import ImageGrab
        except ImportError:
            return
        window = window if window is not None else self.app.root
        window.lift()
        self.app.root.update()
        time.sleep(0.1)
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(window=window.winfo_id()).save(path / f"{name}.png")

    def check_small_layout(self):
        self.app.root.geometry("1040x680")
        self.app.root.update()
        self.assert_visible_actions()
        self.app.root.geometry("1280x764")
        self.app.root.update()

    def create_employee(self, name, role):
        view = self.app.view.current_view
        view.add()
        form = self.modal(EmployeeDialog)
        form.username.set(name)
        form.email.set(name + "@example.org")
        form.password.set("Employee123!")
        form.confirm.set("Employee123!")
        form.role.set(ROLE_LABELS[role])
        self.assert_visible_actions(form)
        form.save()
        self.wait_idle()
        return next(u for u in view.employees.values() if u.username == name)

    def test_four_role_employee_stock_delivery_and_sales_workflow(self):
        app = self.app
        self.assertEqual(app.view.mode, "login")
        self.snapshot("first-run")
        self.login("admin", "Admin1234!")
        self.assertIsInstance(app.view.current_view, EmployeesView)
        self.assertEqual(set(app.view.routes), {"employees", "inventory", "stock_checks", "deliveries", "orders"})
        worker = self.create_employee("testworker", INVENTORY_WORKER)
        checker = self.create_employee("testchecker", STOCK_CHECKER)
        driver = self.create_employee("testdriver", DELIVERY_ASSISTANT)
        self.assertEqual(len(app.view.current_view.employees), 4)
        self.assert_visible_actions()
        self.check_small_layout()
        self.snapshot("admin-employees")
        app.logout()

        self.login(worker.username)
        self.assertEqual(set(app.view.routes), {"inventory", "deliveries", "orders"})
        inventory = app.view.current_view
        inventory.add()
        form = self.modal(ProductDialog)
        form.name.set("Notebook")
        form.category.set("Stationery")
        form.count.set("20")
        form.price.set("12.50")
        self.assert_visible_actions(form)
        form.save()
        self.wait_idle()
        product_id = next(iter(inventory.products))
        self.check_small_layout()
        self.snapshot("inventory-worker")
        app.view.navigate("orders")
        self.wait_idle()
        self.assertEqual(len(app.view.current_view.orders), 0)
        app.view.navigate("deliveries")
        self.wait_idle()
        view = app.view.current_view
        view.assign()
        self.wait_idle()
        form = self.modal(AssignDeliveryDialog)
        form.recipient.set("Store A")
        form.destination.set("12 Warehouse Road")
        form.notes.set("Use the loading bay")
        form.assistant.set(driver.username)
        form.table.tree.selection_set(str(product_id))
        form.count.set("5")
        form.add()
        self.assertEqual(form.manifest.items[0].quantity, 5)
        self.assert_visible_actions(form)
        self.snapshot("assign-delivery", form)
        form.save()
        self.wait_idle()
        self.assertEqual(len(view.deliveries), 1)
        delivery_id = next(iter(view.deliveries))
        self.snapshot("assigned-deliveries")
        app.logout()

        self.login(checker.username)
        self.assertEqual(set(app.view.routes), {"inventory", "stock_checks", "deliveries"})
        inventory = app.view.current_view
        self.assertFalse(inventory.can_edit)
        self.assertEqual(inventory.products[product_id].reserved, 5)
        self.check_small_layout()
        self.snapshot("stock-checker")
        inventory.table.tree.selection_set(str(product_id))
        inventory.record_count()
        form = self.modal(StockCountDialog)
        form.counted.set("18")
        form.notes.set("Two units missing from the shelf")
        self.assert_visible_actions(form)
        form.save()
        self.wait_idle()
        self.assertEqual(inventory.products[product_id].quantity, 20)
        app.view.navigate("stock_checks")
        self.wait_idle()
        checks = app.view.current_view
        check_id = next(iter(checks.checks))
        checks.table.tree.selection_set(str(check_id))
        checks.review()
        review = self.modal(StockReviewDialog)
        buttons = [w.cget("text") for w in self.descendants(review) if w.winfo_class() == "TButton"]
        self.assertNotIn("Apply correction", buttons)
        review.close()
        app.logout()

        self.login("admin", "Admin1234!")
        app.view.navigate("stock_checks")
        self.wait_idle()
        checks = app.view.current_view
        checks.table.tree.selection_set(str(check_id))
        self.snapshot("admin-stock-flags")
        checks.review()
        review = self.modal(StockReviewDialog)
        self.assert_visible_actions(review)
        review.correct()
        self.wait_idle()
        self.assertEqual(len(checks.checks), 0)
        self.assertEqual(app.service.list_products(app.user.user_id)[0].quantity, 18)
        app.logout()

        self.login(driver.username)
        self.assertEqual(set(app.view.routes), {"deliveries"})
        view = app.view.current_view
        self.assertEqual(view.deliveries[delivery_id]["products"], "Notebook × 5")
        self.check_small_layout()
        self.snapshot("truck-delivery-panel")
        view.table.tree.selection_set(str(delivery_id))
        view.open_manifest()
        self.wait_idle()
        manifest = self.modal(DeliveryManifestDialog)
        self.assertEqual(manifest.delivery["items"][0]["quantity"], 5)
        self.assertEqual(manifest.delivery["destination"], "12 Warehouse Road")
        self.assert_visible_actions(manifest)
        self.snapshot("delivery-manifest", manifest)
        manifest.export()
        self.wait_idle()
        self.assertTrue(list(self.db.settings.receipt_dir.glob("delivery_*.txt")))
        manifest.pick_up()
        self.wait_idle()
        self.assertEqual(view.deliveries[delivery_id]["status"], "in_transit")
        view.table.tree.selection_set(str(delivery_id))
        view.open_manifest()
        self.wait_idle()
        self.modal(DeliveryManifestDialog).deliver()
        self.wait_idle()
        self.assertEqual(view.deliveries[delivery_id]["status"], "delivered")
        app.logout()

        self.login(worker.username)
        inventory = app.view.current_view
        self.assertEqual(inventory.products[product_id].quantity, 13)
        self.assertEqual(inventory.products[product_id].reserved, 0)
        app.view.navigate("orders")
        self.wait_idle()
        orders = app.view.current_view
        self.assertEqual(len(orders.orders), 1)
        self.assertEqual(orders.metrics.values["total"].get(), "$62.50")
        self.assertEqual(next(iter(orders.orders.values()))["recipient"], "Store A")
        self.assert_visible_actions()
        self.check_small_layout()
        self.snapshot("worker-orders-sales")
        self.assertEqual(self.messages, [])

    def test_connection_error_has_a_working_retry_action(self):
        with patch.object(self.db, "initialize", side_effect=DatabaseError("Test connection is unavailable")):
            self.app.initialize()
            self.wait_idle()
            self.assertIn("unavailable", self.app.status.get())
        self.app.initialize()
        self.wait_idle()
        self.assertIsInstance(self.app.view, AuthView)
        self.assertEqual(self.app.view.mode, "login")
        self.assertEqual(self.messages, [])

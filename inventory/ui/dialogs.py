"""Product, employee, stock review, and order forms."""

import tkinter as tk
from tkinter import messagebox, ttk

from ..models import currency
from ..receipts import export_receipt
from ..roles import ADMIN, ORDER_STATUS_LABELS, ROLE_LABELS
from .theme import INK
from .widgets import Modal, Table, field


class ProductDialog(Modal):
    def __init__(self, app, product=None, on_saved=None):
        super().__init__(app, "Edit product" if product else "Add product", 600, 650)
        self.product, self.on_saved = product, on_saved
        self.name = tk.StringVar(value=product.name if product else "")
        self.count = tk.StringVar(value=str(product.quantity) if product else "0")
        self.price = tk.StringVar(value=str(product.price) if product else "0.00")
        self.category = tk.StringVar(value=product.category if product else "")
        ttk.Label(self.body, text="Edit product" if product else "Add a product", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        first = field(self.body, "Product name", self.name, 1)
        ttk.Label(self.body, text="Description", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 5))
        self.description = tk.Text(self.body, height=3, wrap="word", relief="solid", borderwidth=1, background="#f8fafc", foreground=INK, font=("Segoe UI", 10), padx=9, pady=7)
        self.description.grid(row=4, column=0, sticky="nsew")
        self.body.rowconfigure(4, weight=1)
        self.description.insert("1.0", product.description if product else "")
        amounts = ttk.Frame(self.body, style="Card.TFrame")
        amounts.grid(row=5, column=0, sticky="ew")
        amounts.columnconfigure((0, 2), weight=1)
        amounts.columnconfigure(1, minsize=15)
        field(amounts, "Stock on hand", self.count, 0, column=0)
        field(amounts, "Unit price ($)", self.price, 0, column=2)
        field(self.body, "Category", self.category, 6)
        ttk.Label(self.body, textvariable=self.error, style="Error.TLabel", wraplength=530).grid(row=8, column=0, sticky="ew", pady=(12, 6))
        actions = ttk.Frame(self.body, style="Card.TFrame")
        actions.grid(row=9, column=0, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="Cancel", command=self.close).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save product", command=self.save, style="Primary.TButton").pack(side="left")
        first.focus_set()

    def save(self):
        values = dict(name=self.name.get(), description=self.description.get("1.0", "end-1c"), count=self.count.get(), price=self.price.get(), category=self.category.get())
        if self.product:
            values.update(product_id=self.product.product_id, expected_version=self.product.version)
        actor, service = self.app.user.user_id, self.app.service
        self.error.set("")

        def saved(_product_id):
            self.close()
            if self.on_saved:
                self.on_saved()

        self.app.run_task(lambda: service.save_product(actor, **values), saved, on_error=self.show_error, status="Saving product…")


class EmployeeDialog(Modal):
    def __init__(self, app, employee=None, on_saved=None):
        super().__init__(app, "Edit employee" if employee else "Add employee", 570, 650 if employee is None else 440)
        self.employee, self.on_saved = employee, on_saved
        self.username = tk.StringVar(value=employee.username if employee else "")
        self.email = tk.StringVar(value=employee.email if employee else "")
        self.password, self.confirm = tk.StringVar(), tk.StringVar()
        self.role = tk.StringVar(value=ROLE_LABELS[employee.role] if employee else "Inventory worker")
        self.active = tk.BooleanVar(value=bool(employee.active) if employee else True)
        ttk.Label(self.body, text="Edit employee" if employee else "Add employee", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        if employee:
            ttk.Label(self.body, text=employee.username, style="CardHeading.TLabel").grid(row=1, column=0, sticky="w", pady=(18, 4))
            ttk.Label(self.body, text=employee.email, style="CardMuted.TLabel").grid(row=2, column=0, sticky="w")
            row = 3
        else:
            field(self.body, "Username", self.username, 1).focus_set()
            field(self.body, "Email", self.email, 3)
            row = 5
        ttk.Label(self.body, text="Employee role", style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=(12, 5))
        ttk.Combobox(self.body, textvariable=self.role, values=list(ROLE_LABELS.values()), state="readonly").grid(row=row + 1, column=0, sticky="ew", ipady=6)
        row += 2
        if employee:
            ttk.Checkbutton(self.body, text="Active employee", variable=self.active, style="Card.TCheckbutton").grid(row=row, column=0, sticky="w", pady=(15, 0))
            row += 1
        else:
            field(self.body, "Password", self.password, row, show="•")
            field(self.body, "Confirm password", self.confirm, row + 2, show="•")
            row += 4
            ttk.Label(self.body, text="8+ characters, uppercase and lowercase letters, a number, and a symbol.", style="CardMuted.TLabel", wraplength=510, font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=(10, 0))
            row += 1
        ttk.Label(self.body, textvariable=self.error, style="Error.TLabel", wraplength=510).grid(row=row, column=0, sticky="ew", pady=10)
        self.body.rowconfigure(row, weight=1)
        actions = ttk.Frame(self.body, style="Card.TFrame")
        actions.grid(row=row + 1, column=0, sticky="e")
        ttk.Button(actions, text="Cancel", command=self.close).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Save employee" if employee else "Add employee", style="Primary.TButton", command=self.save).pack(side="left")

    def save(self):
        if self.app.busy:
            return
        role = next(key for key, label in ROLE_LABELS.items() if label == self.role.get())
        actor, service = self.app.user.user_id, self.app.service.employees
        if self.employee:
            employee_id, active = self.employee.user_id, self.active.get()
            task = lambda: service.update_employee(actor, employee_id, role=role, active=active)
        else:
            name, email, password = self.username.get(), self.email.get(), self.password.get()
            if password != self.confirm.get():
                self.error.set("The passwords do not match.")
                return
            task = lambda: service.create_employee(actor, name, email, password, role)

        def saved(employee):
            self.close()
            if employee.user_id == actor:
                self.app.start_session(employee)
            elif self.on_saved:
                self.on_saved()

        self.app.run_task(task, saved, on_error=self.show_error, status="Saving employee…")


class StockCountDialog(Modal):
    def __init__(self, app, product, on_saved):
        super().__init__(app, "Record stock count", 560, 470)
        self.product, self.on_saved = product, on_saved
        self.counted, self.notes = tk.StringVar(), tk.StringVar()
        ttk.Label(self.body, text="Record stock count", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.body, text=product.name, style="CardHeading.TLabel").grid(row=1, column=0, sticky="w", pady=(20, 6))
        ttk.Label(self.body, text=f"Recorded stock: {product.quantity:,}  ·  Reserved: {product.reserved:,}", style="CardMuted.TLabel").grid(row=2, column=0, sticky="w")
        field(self.body, "Physical count", self.counted, 3).focus_set()
        field(self.body, "Notes (optional)", self.notes, 5)
        ttk.Label(self.body, textvariable=self.error, style="Error.TLabel", wraplength=500).grid(row=7, column=0, sticky="ew", pady=12)
        self.body.rowconfigure(7, weight=1)
        actions = ttk.Frame(self.body, style="Card.TFrame")
        actions.grid(row=8, column=0, sticky="e")
        ttk.Button(actions, text="Cancel", command=self.close).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Record count", command=self.save, style="Primary.TButton").pack(side="left")

    def save(self):
        actor, service = self.app.user.user_id, self.app.service.stock
        product_id, version, counted, notes = self.product.product_id, self.product.version, self.counted.get(), self.notes.get()

        def saved(_check_id):
            self.close()
            self.on_saved()

        self.app.run_task(lambda: service.record_count(actor, product_id, counted, expected_version=version, notes=notes), saved, on_error=self.show_error, status="Recording stock count…")


class StockReviewDialog(Modal):
    def __init__(self, app, check, on_saved):
        super().__init__(app, f"Stock count #{check['check_id']}", 570, 500)
        self.check, self.on_saved = check, on_saved
        ttk.Label(self.body, text=f"Stock count #{check['check_id']}", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        details = [
            ("Product", check["product_name"]), ("Recorded stock", check["expected_quantity"]),
            ("Physical count", check["counted_quantity"]), ("Difference", f"{check['difference']:+,}"),
            ("Checked by", check["checked_by_name"]), ("Status", check["status"].capitalize()),
        ]
        for row, (label, value) in enumerate(details, 1):
            ttk.Label(self.body, text=f"{label}: {value}", style="Card.TLabel", wraplength=510).grid(row=row, column=0, sticky="w", pady=(12, 0))
        notes = tk.Text(self.body, height=3, wrap="word", borderwidth=0, background="#f8fafc", font=("Segoe UI", 10), padx=8, pady=7)
        notes.grid(row=7, column=0, sticky="ew", pady=(12, 0))
        notes.insert("1.0", check["notes"] or "No notes")
        notes.configure(state="disabled")
        ttk.Label(self.body, textvariable=self.error, style="Error.TLabel", wraplength=510).grid(row=8, column=0, sticky="ew", pady=12)
        self.body.rowconfigure(8, weight=1)
        actions = ttk.Frame(self.body, style="Card.TFrame")
        actions.grid(row=9, column=0, sticky="e")
        ttk.Button(actions, text="Close", command=self.close).pack(side="left", padx=(0, 8))
        if app.user.role == ADMIN and check["status"] == "flagged":
            ttk.Button(actions, text="Apply correction", command=self.correct, style="Primary.TButton").pack(side="left")

    def correct(self):
        if self.app.busy:
            return
        if not messagebox.askyesno("Correct stock", f"Set stock for {self.check['product_name']} to {self.check['counted_quantity']:,}?", parent=self):
            return
        actor, check_id, service = self.app.user.user_id, self.check["check_id"], self.app.service.stock

        def saved(_result):
            self.close()
            self.on_saved()

        self.app.run_task(lambda: service.correct_count(actor, check_id), saved, on_error=self.show_error, status="Applying stock correction…")


class OrderDialog(Modal):
    def __init__(self, app, order, receipt_path=None, export_error=None):
        super().__init__(app, f"Order #{order['order_id']}", 870, 590)
        self.order = order
        ttk.Label(self.body, text=f"Order #{order['order_id']}", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        summary = f"Recipient: {order['recipient']}  ·  {ORDER_STATUS_LABELS[order['status']]}\nCreated by: {order['username']}  ·  {order['order_date']}"
        ttk.Label(self.body, text=summary, style="CardMuted.TLabel", wraplength=790).grid(row=1, column=0, sticky="w", pady=(10, 16))
        table = Table(self.body, [("name", "PRODUCT", 240, "w"), ("category", "CATEGORY", 120, "w"), ("quantity", "UNITS", 70, "e"), ("price", "UNIT PRICE", 100, "e"), ("total", "LINE TOTAL", 110, "e")], height=7)
        table.grid(row=2, column=0, sticky="nsew")
        self.body.rowconfigure(2, weight=1)
        table.replace([(index, (item["product_name"], item["category"], item["quantity"], currency(item["unit_price"]), currency(item["price"])), ()) for index, item in enumerate(order["items"], 1)])
        ttk.Label(self.body, text=f"Order value: {currency(order['total_price'])}", style="CardHeading.TLabel").grid(row=3, column=0, sticky="e", pady=(18, 0))
        self.message = tk.StringVar(value=f"Receipt saved: {receipt_path}" if receipt_path else "")
        self.message_label = ttk.Label(self.body, textvariable=self.message, style="CardMuted.TLabel", wraplength=790)
        self.message_label.grid(row=4, column=0, sticky="w", pady=13)
        if export_error:
            self.message.set("The order is saved. Check the receipt folder and export again.")
            self.message_label.configure(style="Error.TLabel")
        actions = ttk.Frame(self.body, style="Card.TFrame")
        actions.grid(row=5, column=0, sticky="e")
        ttk.Button(actions, text="Close", command=self.close).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Export receipt", command=self.export, style="Primary.TButton").pack(side="left")

    def export(self):
        order, directory = self.order, self.app.settings.receipt_dir

        def saved(path):
            self.message_label.configure(style="Success.TLabel")
            self.message.set(f"Receipt saved: {path}")

        self.app.run_task(lambda: export_receipt(order, directory), saved, on_error=lambda exc: self.message.set(str(exc)), status="Exporting receipt…")

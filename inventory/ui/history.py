"""Order and completed sales reporting for admins and inventory workers."""

from decimal import Decimal
from tkinter import messagebox, ttk

from ..models import currency
from ..receipts import export_receipt
from ..roles import ORDER_STATUS_LABELS
from .widgets import Metrics, Table, view_header


class OrdersView(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent)
        self.app, self.orders = app, {}
        view_header(self, "Orders & sales")
        self.metrics = Metrics(self, [("count", "Orders"), ("total", "Completed sales"), ("pending", "Orders to deliver")])
        self.metrics.pack(fill="x", pady=(0, 20))
        card = ttk.Frame(self, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)
        self.table = Table(card, [("id", "ORDER", 75, "w"), ("recipient", "RECIPIENT", 170, "w"), ("creator", "CREATED BY", 150, "w"), ("date", "DATE", 180, "w"), ("status", "STATUS", 140, "w"), ("quantity", "UNITS", 70, "e"), ("total", "ORDER VALUE", 130, "e")], empty="No orders yet. Assign a delivery to create an order.")
        self.table.grid(row=0, column=0, sticky="nsew")
        self.table.tree.bind("<Double-1>", lambda _event: self.details())
        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=1, column=0, sticky="e", pady=(15, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Export receipt", command=self.export).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="View order", command=self.details, style="Primary.TButton").pack(side="left")
        self.after_idle(self.refresh)

    def refresh(self):
        actor, service = self.app.user.user_id, self.app.service.sales

        def loaded(orders):
            self.orders = {row["order_id"]: row for row in orders}
            self.table.replace([(row["order_id"], (f"#{row['order_id']}", row["recipient"], row["username"], row["order_date"], ORDER_STATUS_LABELS[row["status"]], row["item_count"], currency(row["total_price"])), ()) for row in orders])
            completed = sum((row["total_price"] for row in orders if row["status"] == "completed"), Decimal("0.00"))
            pending = sum(row["status"] in {"pending_delivery", "in_transit"} for row in orders)
            self.metrics.set(count=len(orders), total=currency(completed), pending=pending)

        self.app.run_task(lambda: service.list_orders(actor), loaded, status="Loading orders and sales…")

    def selected(self):
        selected = self.table.selected()
        if selected is None:
            messagebox.showinfo("Select an order", "Select an order in the table first.", parent=self.app.root)
        return selected

    def details(self):
        if not self.app.busy:
            selected = self.selected()
            if selected is not None:
                self.app.show_order(selected)

    def export(self):
        if self.app.busy:
            return
        selected = self.selected()
        if selected is None:
            return
        actor, service, directory = self.app.user.user_id, self.app.service.sales, self.app.settings.receipt_dir
        self.app.run_task(lambda: export_receipt(service.order_detail(actor, selected), directory), lambda path: messagebox.showinfo("Receipt exported", f"Receipt saved:\n{path}", parent=self.app.root), status="Exporting receipt…")

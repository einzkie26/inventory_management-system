"""Inventory worker tools and the stock checker's read-only stock panel."""

import tkinter as tk
from tkinter import messagebox, ttk

from ..models import currency
from ..roles import ADMIN, INVENTORY_ROLES, STOCK_CHECKER, STOCK_ROLES
from .dialogs import ProductDialog, StockCountDialog
from .widgets import Metrics, Table, view_header


class InventoryView(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent)
        self.app, self.products = app, {}
        self.can_edit = app.user.role in INVENTORY_ROLES
        self.can_count = app.user.role in STOCK_ROLES
        self.search, self.archived = tk.StringVar(), tk.BooleanVar(value=False)
        title = "Stock checker panel" if app.user.role == STOCK_CHECKER else "Inventory worker panel" if app.user.role != ADMIN else "Inventory overview"
        view_header(self, title)
        labels = [("stock", "Stock on hand"), ("reserved", "Reserved for delivery"), ("available", "Available stock"), ("fourth", "Count flags" if app.user.role == STOCK_CHECKER else "Completed sales")]
        self.metrics = Metrics(self, labels)
        self.metrics.pack(fill="x", pady=(0, 20))
        card = ttk.Frame(self, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(card, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        ttk.Label(toolbar, text="Find products", style="Card.TLabel").pack(side="left", padx=(0, 10))
        entry = ttk.Entry(toolbar, textvariable=self.search, width=18)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self.refresh())
        ttk.Button(toolbar, text="Search", command=self.refresh).pack(side="left", padx=(8, 12))
        if self.can_edit:
            ttk.Checkbutton(toolbar, text="Show archived", variable=self.archived, command=self.refresh, style="Card.TCheckbutton").pack(side="left", padx=(0, 12))
            ttk.Button(toolbar, text="+ Add product", style="Primary.TButton", command=self.add).pack(side="left")
        columns = [("id", "ID", 55, "w"), ("name", "PRODUCT", 190, "w"), ("category", "CATEGORY", 120, "w"), ("quantity", "ON HAND", 85, "e"), ("reserved", "RESERVED", 90, "e"), ("available", "AVAILABLE", 90, "e")]
        if self.can_edit:
            columns.append(("price", "UNIT PRICE", 100, "e"))
        columns += [("status", "STATUS", 100, "w"), ("description", "DESCRIPTION", 230, "w")]
        self.table = Table(card, columns, empty="No products found.")
        self.table.grid(row=1, column=0, sticky="nsew")
        self.table.tree.bind("<Double-1>", lambda _event: self.edit() if self.can_edit else self.record_count())
        footer = ttk.Frame(card, style="Card.TFrame")
        footer.grid(row=2, column=0, sticky="ew", pady=(15, 0))
        self.count = tk.StringVar(value="Loading products…")
        ttk.Label(footer, textvariable=self.count, style="CardMuted.TLabel").pack(side="left")
        ttk.Button(footer, text="Refresh", command=self.refresh).pack(side="right")
        if self.can_count:
            ttk.Button(footer, text="Record count", command=self.record_count).pack(side="right", padx=8)
        if self.can_edit:
            ttk.Button(footer, text="Archive / restore", command=self.toggle_active).pack(side="right", padx=(8, 0))
            ttk.Button(footer, text="Edit selected", command=self.edit).pack(side="right")
        self.after_idle(self.refresh)

    def refresh(self):
        search, archived, actor, service = self.search.get(), self.archived.get(), self.app.user.user_id, self.app.service

        def loaded(result):
            products, stats = result
            self.products = {p.product_id: p for p in products}
            rows = []
            for p in products:
                values = [p.product_id, p.name, p.category, f"{p.quantity:,}", f"{p.reserved:,}", f"{p.available:,}"]
                if self.can_edit:
                    values.append(currency(p.price))
                values += ["Archived" if not p.active else "Low stock" if p.available <= 5 else "In stock", p.description]
                tags = ("archived",) if not p.active else ("low",) if p.available <= 5 else ()
                rows.append((p.product_id, values, tags))
            self.table.replace(rows)
            self.metrics.set(stock=f"{stats['total_units']:,}", reserved=f"{stats['reserved_units']:,}", available=f"{stats['available_units']:,}", fourth=stats["flagged_checks"] if not self.can_edit else currency(stats["total_sales"]))
            self.count.set(f"{len(products):,} products")

        self.app.run_task(lambda: (service.list_products(actor, search, include_archived=archived), service.dashboard(actor)), loaded, status="Refreshing inventory…")

    def selected(self):
        product = self.products.get(self.table.selected())
        if product is None:
            messagebox.showinfo("Select a product", "Select a product in the table first.", parent=self.app.root)
        return product

    def add(self):
        if self.can_edit and not self.app.busy:
            ProductDialog(self.app, on_saved=self.refresh)

    def edit(self):
        if self.app.busy or not self.can_edit:
            return
        product = self.selected()
        if product:
            ProductDialog(self.app, product, self.refresh)

    def record_count(self):
        if self.app.busy or not self.can_count:
            return
        product = self.selected()
        if product:
            StockCountDialog(self.app, product, self.refresh)

    def toggle_active(self):
        if self.app.busy or not self.can_edit:
            return
        product = self.selected()
        if product is None:
            return
        action = "Archive" if product.active else "Restore"
        if messagebox.askyesno(f"{action} product", f"{action} {product.name}? Existing orders and delivery history will be preserved.", parent=self.app.root):
            actor, service = self.app.user.user_id, self.app.service
            self.app.run_task(lambda: service.set_product_active(actor, product.product_id, not product.active), lambda _result: self.refresh(), status=f"{action} product…")

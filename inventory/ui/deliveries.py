"""Delivery management and the truck delivery assistant's panel."""

import tkinter as tk
from tkinter import messagebox, ttk

from ..roles import DELIVERY_ASSISTANT, DELIVERY_STATUS_LABELS, INVENTORY_ROLES
from .delivery_dialogs import AssignDeliveryDialog, DeliveryManifestDialog, ReassignDeliveryDialog
from .widgets import Metrics, Table, view_header


class DeliveriesView(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent)
        self.app, self.deliveries = app, {}
        self.can_assign = app.user.role in INVENTORY_ROLES
        self.status = tk.StringVar(value="All statuses")
        view_header(self, "Truck delivery panel" if app.user.role == DELIVERY_ASSISTANT else "Deliveries")
        self.metrics = Metrics(self, [("assigned", "Assigned"), ("in_transit", "In transit"), ("delivered", "Delivered"), ("units", "Units to deliver")])
        self.metrics.pack(fill="x", pady=(0, 20))
        card = ttk.Frame(self, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(card, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        ttk.Label(toolbar, text="Delivery status", style="Card.TLabel").pack(side="left", padx=(0, 10))
        statuses = ttk.Combobox(toolbar, textvariable=self.status, values=["All statuses", *DELIVERY_STATUS_LABELS.values()], state="readonly", width=18)
        statuses.pack(side="left", ipady=6)
        statuses.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        if self.can_assign:
            ttk.Button(toolbar, text="Assign delivery", style="Primary.TButton", command=self.assign).pack(side="right")
        self.table = Table(card, [("id", "DELIVERY", 85, "w"), ("products", "PRODUCTS TO DELIVER", 300, "w"), ("quantity", "UNITS", 70, "e"), ("recipient", "RECIPIENT", 150, "w"), ("destination", "DESTINATION", 210, "w"), ("assistant", "ASSISTANT", 150, "w"), ("status", "STATUS", 110, "w")], empty="No deliveries assigned yet.")
        self.table.grid(row=1, column=0, sticky="nsew")
        self.table.tree.bind("<Double-1>", lambda _event: self.open_manifest())
        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="e", pady=(15, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="left", padx=(0, 8))
        if self.can_assign:
            ttk.Button(actions, text="Reassign", command=self.reassign).pack(side="left", padx=(0, 8))
            ttk.Button(actions, text="Cancel delivery", command=self.cancel, style="Danger.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Open manifest", command=self.open_manifest, style="Primary.TButton").pack(side="left")
        self.after_idle(self.refresh)

    def refresh(self):
        actor, label, service = self.app.user.user_id, self.status.get(), self.app.service.deliveries
        status = next((key for key, value in DELIVERY_STATUS_LABELS.items() if value == label), None)

        def loaded(rows):
            self.deliveries = {row["delivery_id"]: row for row in rows}
            self.table.replace([(row["delivery_id"], (f"#{row['delivery_id']}", row["products"], row["units"], row["recipient"], row["destination"], row["assistant_name"], DELIVERY_STATUS_LABELS[row["status"]]), ()) for row in rows])
            self.metrics.set(**{key: sum(row["status"] == key for row in rows) for key in ("assigned", "in_transit", "delivered")}, units=sum(row["units"] for row in rows if row["status"] in {"assigned", "in_transit"}))

        self.app.run_task(lambda: service.list_deliveries(actor, status), loaded, status="Loading deliveries…")

    def selected(self):
        delivery = self.deliveries.get(self.table.selected())
        if delivery is None:
            messagebox.showinfo("Select a delivery", "Select a delivery in the table first.", parent=self.app.root)
        return delivery

    def assign(self):
        if self.app.busy or not self.can_assign:
            return
        actor, service = self.app.user.user_id, self.app.service

        def loaded(result):
            products, assistants = result
            if not assistants:
                messagebox.showinfo("Delivery assistant required", "An admin must add an active Truck delivery assistant employee first.", parent=self.app.root)
                return
            AssignDeliveryDialog(self.app, products, assistants, self.refresh)

        self.app.run_task(lambda: (service.list_products(actor), service.employees.delivery_assistants(actor)), loaded, status="Loading products and assistants…")

    def open_manifest(self):
        if self.app.busy:
            return
        delivery = self.selected()
        if delivery:
            actor, service, delivery_id = self.app.user.user_id, self.app.service.deliveries, delivery["delivery_id"]
            self.app.run_task(lambda: service.delivery_detail(actor, delivery_id), lambda detail: DeliveryManifestDialog(self.app, detail, self.refresh), status="Loading product manifest…")

    def cancel(self):
        if self.app.busy or not self.can_assign:
            return
        delivery = self.selected()
        if delivery and messagebox.askyesno("Cancel delivery", f"Cancel delivery #{delivery['delivery_id']} and release its reserved products?", parent=self.app.root):
            actor, delivery_id, service = self.app.user.user_id, delivery["delivery_id"], self.app.service.deliveries
            self.app.run_task(lambda: service.cancel_delivery(actor, delivery_id), lambda _result: self.refresh(), status="Cancelling delivery…")

    def reassign(self):
        if self.app.busy or not self.can_assign:
            return
        delivery = self.selected()
        if delivery:
            actor, service = self.app.user.user_id, self.app.service.employees
            self.app.run_task(lambda: service.delivery_assistants(actor), lambda assistants: ReassignDeliveryDialog(self.app, delivery, assistants, self.refresh), status="Loading assistants…")

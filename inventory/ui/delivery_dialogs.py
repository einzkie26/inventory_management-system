"""Delivery assignment, product manifests, and assistant actions."""

import tkinter as tk
from tkinter import messagebox, ttk

from ..errors import InventoryError
from ..models import Manifest, currency
from ..receipts import export_manifest
from ..roles import ADMIN, DELIVERY_ASSISTANT, DELIVERY_STATUS_LABELS
from .widgets import Modal, Table, field


class AssignDeliveryDialog(Modal):
    def __init__(self, app, products, assistants, on_saved):
        super().__init__(app, "Assign delivery", 1080, 700)
        self.minsize(920, 620)
        self.on_saved, self.products, self.assistants = on_saved, {p.product_id: p for p in products}, assistants
        self.manifest = Manifest()
        self.recipient, self.destination, self.notes = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.assistant = tk.StringVar(value=assistants[0]["username"] if assistants else "")
        self.count = tk.StringVar(value="1")
        self.total = tk.StringVar(value="$0.00")
        ttk.Label(self.body, text="Assign delivery", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        details = ttk.Frame(self.body, style="Card.TFrame")
        details.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        details.columnconfigure((0, 2), weight=1, uniform="details")
        details.columnconfigure(1, minsize=18)
        field(details, "Recipient", self.recipient, 0)
        ttk.Label(details, text="Delivery assistant", style="Card.TLabel").grid(row=0, column=2, sticky="w", pady=(12, 5))
        ttk.Combobox(details, textvariable=self.assistant, values=[row["username"] for row in assistants], state="readonly").grid(row=1, column=2, sticky="ew", ipady=6)
        field(details, "Destination", self.destination, 2)
        field(details, "Delivery notes (optional)", self.notes, 2, column=2)
        panes = ttk.Panedwindow(self.body, orient="horizontal")
        panes.grid(row=2, column=0, sticky="nsew")
        self.body.rowconfigure(2, weight=1)
        source = ttk.Frame(panes, style="Card.TFrame", padding=(0, 0, 12, 0))
        selected = ttk.Frame(panes, style="Card.TFrame", padding=(12, 0, 0, 0))
        panes.add(source, weight=3)
        panes.add(selected, weight=2)
        for pane in (source, selected):
            pane.columnconfigure(0, weight=1)
            pane.rowconfigure(1, weight=1)
        ttk.Label(source, text="Available products", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.table = Table(source, [("name", "PRODUCT", 190, "w"), ("category", "CATEGORY", 100, "w"), ("available", "AVAILABLE", 90, "e"), ("price", "UNIT PRICE", 100, "e")], empty="No products are available for delivery.", height=6)
        self.table.grid(row=1, column=0, sticky="nsew")
        self.table.replace([(p.product_id, (p.name, p.category, p.available, currency(p.price)), ()) for p in products])
        self.table.tree.bind("<Double-1>", lambda _event: self.add())
        controls = ttk.Frame(source, style="Card.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(controls, text="Quantity", style="Card.TLabel").pack(side="left", padx=(0, 8))
        ttk.Spinbox(controls, from_=1, to=2_147_483_647, textvariable=self.count, width=6).pack(side="left")
        ttk.Button(controls, text="Add product", command=self.add).pack(side="right")
        ttk.Label(selected, text="Products to deliver", style="CardHeading.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.manifest_table = Table(selected, [("name", "PRODUCT", 190, "w"), ("quantity", "QUANTITY", 85, "e"), ("price", "VALUE", 100, "e")], empty="Add products from the list.", height=6)
        self.manifest_table.grid(row=1, column=0, sticky="nsew")
        controls = ttk.Frame(selected, style="Card.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(controls, text="Remove selected", command=self.remove).pack(side="left")
        ttk.Label(controls, textvariable=self.total, style="CardHeading.TLabel").pack(side="right")
        ttk.Label(self.body, textvariable=self.error, style="Error.TLabel", wraplength=1000).grid(row=3, column=0, sticky="ew", pady=12)
        actions = ttk.Frame(self.body, style="Card.TFrame")
        actions.grid(row=4, column=0, sticky="e")
        ttk.Button(actions, text="Cancel", command=self.close).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Assign delivery", command=self.save, style="Primary.TButton").pack(side="left")

    def render_items(self):
        self.manifest_table.replace([(item.product.product_id, (item.product.name, item.quantity, currency(item.total)), ()) for item in self.manifest.items])
        self.total.set(currency(self.manifest.total))

    def add(self):
        if self.app.busy:
            return
        product = self.products.get(self.table.selected())
        if product is None:
            self.error.set("Select a product from the available products first.")
            return
        try:
            self.manifest.add(product, self.count.get())
        except InventoryError as exc:
            self.error.set(str(exc))
            return
        self.error.set("")
        self.count.set("1")
        self.render_items()

    def remove(self):
        if not self.app.busy:
            self.manifest.remove(self.manifest_table.selected())
            self.render_items()

    def save(self):
        if self.app.busy:
            return
        assistant_id = next((row["user_id"] for row in self.assistants if row["username"] == self.assistant.get()), None)
        if assistant_id is None:
            self.error.set("Select an active delivery assistant.")
            return
        actor, service, manifest = self.app.user.user_id, self.app.service.deliveries, self.manifest
        recipient, destination, notes = self.recipient.get(), self.destination.get(), self.notes.get()

        def saved(_delivery_id):
            self.close()
            self.on_saved()

        self.app.run_task(lambda: service.create_delivery(actor, assistant_id, recipient=recipient, destination=destination, manifest=manifest, notes=notes), saved, on_error=self.show_error, status="Assigning delivery…")


class DeliveryManifestDialog(Modal):
    def __init__(self, app, delivery, on_changed):
        super().__init__(app, f"Delivery #{delivery['delivery_id']}", 850, 670)
        self.minsize(740, 620)
        self.delivery, self.on_changed = delivery, on_changed
        ttk.Label(self.body, text=f"Delivery #{delivery['delivery_id']}", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        summary = (
            f"Status: {DELIVERY_STATUS_LABELS[delivery['status']]}  ·  Assistant: {delivery['assistant_name']}\n"
            f"Recipient: {delivery['recipient']}\nDestination: {delivery['destination']}"
        )
        ttk.Label(self.body, text=summary, style="Card.TLabel", wraplength=790).grid(row=1, column=0, sticky="w", pady=(14, 16))
        table = Table(self.body, [("name", "PRODUCT TO DELIVER", 340, "w"), ("category", "CATEGORY", 190, "w"), ("quantity", "QUANTITY", 120, "e")], height=6)
        table.grid(row=2, column=0, sticky="nsew")
        self.body.rowconfigure(2, weight=1)
        table.replace([(index, (item["product_name"], item["category"], f"{item['quantity']:,}"), ()) for index, item in enumerate(delivery["items"], 1)])
        notes = tk.Text(self.body, height=2, wrap="word", borderwidth=0, background="#f8fafc", font=("Segoe UI", 10), padx=10, pady=8)
        notes.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        notes.insert("1.0", "Delivery notes: " + (delivery["notes"] or "—"))
        notes.configure(state="disabled")
        ttk.Label(self.body, text="Delivery history", style="CardHeading.TLabel").grid(row=4, column=0, sticky="w", pady=(12, 6))
        history = tk.Text(self.body, height=3, wrap="word", borderwidth=0, background="#f8fafc", font=("Segoe UI", 9), padx=10, pady=8)
        history.grid(row=5, column=0, sticky="ew")
        history.insert("1.0", "\n".join(f"{event['created_at']} · {event['actor_name']} · {event['notes']}" for event in delivery["events"]))
        history.configure(state="disabled")
        history.see("end")
        ttk.Label(self.body, textvariable=self.error, style="Error.TLabel", wraplength=790).grid(row=6, column=0, sticky="ew", pady=12)
        actions = ttk.Frame(self.body, style="Card.TFrame")
        actions.grid(row=7, column=0, sticky="e")
        ttk.Button(actions, text="Close", command=self.close).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Export manifest", command=self.export).pack(side="left", padx=(0, 8))
        if app.user.role in {ADMIN, DELIVERY_ASSISTANT}:
            if delivery["status"] == "assigned":
                ttk.Button(actions, text="Mark picked up", command=self.pick_up, style="Primary.TButton").pack(side="left")
            elif delivery["status"] == "in_transit":
                ttk.Button(actions, text="Mark delivered", command=self.deliver, style="Primary.TButton").pack(side="left")

    def change(self, method, question):
        if self.app.busy or not messagebox.askyesno("Update delivery", question, parent=self):
            return
        actor, delivery_id = self.app.user.user_id, self.delivery["delivery_id"]

        def saved(_result):
            self.close()
            self.on_changed()

        self.app.run_task(lambda: method(actor, delivery_id), saved, on_error=self.show_error, status="Updating delivery…")

    def pick_up(self):
        self.change(self.app.service.deliveries.mark_picked_up, "Confirm these products have been picked up? This will reduce warehouse stock.")

    def deliver(self):
        self.change(self.app.service.deliveries.mark_delivered, "Mark these products as delivered to the recipient?")

    def export(self):
        delivery, directory = self.delivery, self.app.settings.receipt_dir
        self.app.run_task(lambda: export_manifest(delivery, directory), lambda path: self.app.set_status(f"Manifest saved: {path}"), on_error=self.show_error, status="Exporting manifest…")


class ReassignDeliveryDialog(Modal):
    def __init__(self, app, delivery, assistants, on_saved):
        super().__init__(app, "Reassign delivery", 530, 340)
        self.delivery, self.assistants, self.on_saved = delivery, assistants, on_saved
        self.assistant = tk.StringVar(value=delivery["assistant_name"])
        ttk.Label(self.body, text=f"Reassign delivery #{delivery['delivery_id']}", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self.body, text="Delivery assistant", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(20, 7))
        ttk.Combobox(self.body, textvariable=self.assistant, values=[row["username"] for row in assistants], state="readonly").grid(row=2, column=0, sticky="ew", ipady=6)
        ttk.Label(self.body, textvariable=self.error, style="Error.TLabel", wraplength=470).grid(row=3, column=0, sticky="ew", pady=12)
        self.body.rowconfigure(3, weight=1)
        actions = ttk.Frame(self.body, style="Card.TFrame")
        actions.grid(row=4, column=0, sticky="e")
        ttk.Button(actions, text="Cancel", command=self.close).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Reassign", command=self.save, style="Primary.TButton").pack(side="left")

    def save(self):
        actor, service, delivery_id = self.app.user.user_id, self.app.service.deliveries, self.delivery["delivery_id"]
        assistant_id = next((row["user_id"] for row in self.assistants if row["username"] == self.assistant.get()), None)
        if assistant_id is None:
            self.error.set("Select a delivery assistant.")
            return

        def saved(_result):
            self.close()
            self.on_saved()

        self.app.run_task(lambda: service.reassign_delivery(actor, delivery_id, assistant_id), saved, on_error=self.show_error, status="Reassigning delivery…")

"""The admin panel and its employee roster."""

import tkinter as tk
from tkinter import messagebox, ttk

from ..roles import ADMIN, DELIVERY_ASSISTANT, INVENTORY_WORKER, ROLE_LABELS, STOCK_CHECKER
from .dialogs import EmployeeDialog
from .widgets import Metrics, Table, view_header


class EmployeesView(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent)
        self.app, self.employees = app, {}
        self.search, self.role = tk.StringVar(), tk.StringVar(value="All roles")
        view_header(self, "Admin panel")
        self.metrics = Metrics(self, [(INVENTORY_WORKER, "Inventory workers"), (STOCK_CHECKER, "Stock checkers"), (DELIVERY_ASSISTANT, "Delivery assistants"), (ADMIN, "Admins")])
        self.metrics.pack(fill="x", pady=(0, 20))
        card = ttk.Frame(self, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(card, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        ttk.Label(toolbar, text="Employees", style="CardHeading.TLabel").pack(side="left", padx=(0, 12))
        entry = ttk.Entry(toolbar, textvariable=self.search, width=12)
        entry.pack(side="left", fill="x", expand=True)
        entry.bind("<Return>", lambda _event: self.refresh())
        ttk.Button(toolbar, text="Search", command=self.refresh).pack(side="left", padx=8)
        roles = ttk.Combobox(toolbar, textvariable=self.role, values=["All roles", *ROLE_LABELS.values()], state="readonly", width=21)
        roles.pack(side="left", padx=(0, 8), ipady=6)
        roles.bind("<<ComboboxSelected>>", lambda _event: self.refresh())
        ttk.Button(toolbar, text="Add employee", command=self.add, style="Primary.TButton").pack(side="left")
        self.table = Table(card, [("id", "ID", 60, "w"), ("username", "EMPLOYEE", 170, "w"), ("email", "EMAIL", 240, "w"), ("role", "ROLE", 220, "w"), ("status", "STATUS", 100, "w")], empty="No employees match this search.")
        self.table.grid(row=1, column=0, sticky="nsew")
        self.table.tree.bind("<Double-1>", lambda _event: self.edit())
        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew", pady=(15, 0))
        self.count = tk.StringVar()
        ttk.Label(actions, textvariable=self.count, style="CardMuted.TLabel").pack(side="left")
        ttk.Button(actions, text="Edit employee", command=self.edit).pack(side="right")
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="right", padx=8)
        self.after_idle(self.refresh)

    def refresh(self):
        actor, search, label, service = self.app.user.user_id, self.search.get(), self.role.get(), self.app.service.employees
        role = next((key for key, value in ROLE_LABELS.items() if value == label), None)

        def loaded(employees):
            self.employees = {user.user_id: user for user in employees}
            self.table.replace([(u.user_id, (u.user_id, u.username, u.email, ROLE_LABELS[u.role], "Active" if u.active else "Inactive"), () if u.active else ("archived",)) for u in employees])
            self.metrics.set(**{key: sum(u.role == key and bool(u.active) for u in employees) for key in ROLE_LABELS})
            self.count.set(f"{len(employees):,} employee accounts")

        self.app.run_task(lambda: service.list_employees(actor, search, role), loaded, status="Loading employees…")

    def add(self):
        if not self.app.busy:
            EmployeeDialog(self.app, on_saved=self.refresh)

    def edit(self):
        if self.app.busy:
            return
        employee = self.employees.get(self.table.selected())
        if employee is None:
            messagebox.showinfo("Select an employee", "Select an employee in the table first.", parent=self.app.root)
            return
        EmployeeDialog(self.app, employee, self.refresh)

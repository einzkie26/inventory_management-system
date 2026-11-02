"""A single application window with role-aware navigation."""

from tkinter import ttk

from ..roles import ADMIN, DELIVERY_ASSISTANT, INVENTORY_WORKER, ROLE_LABELS, STOCK_CHECKER
from .deliveries import DeliveriesView
from .employees import EmployeesView
from .history import OrdersView
from .inventory import InventoryView
from .stock import StockChecksView


class Shell(ttk.Frame):
    def __init__(self, app):
        super().__init__(app.container)
        self.app, self.current_view = app, None
        self.pack(fill="both", expand=True)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=190, padding=(16, 26))
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(3, weight=1)
        ttk.Label(sidebar, text="Inventory", style="SidebarBrand.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(sidebar, text="MANAGEMENT SYSTEM", style="SidebarMuted.TLabel", font=("Segoe UI", 8)).grid(row=1, column=0, sticky="w", pady=(4, 30))
        nav = ttk.Frame(sidebar, style="Sidebar.TFrame")
        nav.grid(row=2, column=0, sticky="new")
        self.routes = {
            ADMIN: {"employees": EmployeesView, "inventory": InventoryView, "stock_checks": StockChecksView, "deliveries": DeliveriesView, "orders": OrdersView},
            INVENTORY_WORKER: {"inventory": InventoryView, "deliveries": DeliveriesView, "orders": OrdersView},
            STOCK_CHECKER: {"inventory": InventoryView, "stock_checks": StockChecksView, "deliveries": DeliveriesView},
            DELIVERY_ASSISTANT: {"deliveries": DeliveriesView},
        }[app.user.role]
        labels = {"employees": "Employees", "inventory": "Check stock" if app.user.role == STOCK_CHECKER else "Inventory", "stock_checks": "Stock count flags", "deliveries": "My deliveries" if app.user.role == DELIVERY_ASSISTANT else "Deliveries", "orders": "Orders & sales"}
        self.buttons = {}
        for key in self.routes:
            button = ttk.Button(nav, text=labels[key], style="Nav.TButton", command=lambda name=key: self.navigate(name))
            button.pack(fill="x", pady=3)
            self.buttons[key] = button
        footer = ttk.Frame(sidebar, style="Sidebar.TFrame")
        footer.grid(row=4, column=0, sticky="sew")
        ttk.Label(footer, text=app.user.username, style="Sidebar.TLabel", wraplength=155, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(footer, text=ROLE_LABELS[app.user.role], style="SidebarMuted.TLabel", wraplength=155).pack(anchor="w", pady=(3, 20))
        ttk.Button(footer, text="Sign out", style="Nav.TButton", command=app.logout).pack(fill="x")
        ttk.Label(footer, text="MySQL / XAMPP", style="SidebarMuted.TLabel", font=("Segoe UI", 8)).pack(anchor="w", pady=(18, 0))
        self.content = ttk.Frame(self, padding=(22, 22))
        self.content.grid(row=0, column=1, sticky="nsew")
        self.navigate(next(iter(self.routes)))

    def navigate(self, route):
        if self.app.busy:
            return
        if self.current_view is not None:
            self.current_view.destroy()
        for key, button in self.buttons.items():
            button.configure(style="SelectedNav.TButton" if key == route else "Nav.TButton")
        self.current_view = self.routes[route](self.app, self.content)
        self.current_view.pack(fill="both", expand=True)

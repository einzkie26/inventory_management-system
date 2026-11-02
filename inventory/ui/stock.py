"""Stock count flags for checker review and admin correction."""

import tkinter as tk
from tkinter import messagebox, ttk

from .dialogs import StockReviewDialog
from .widgets import Metrics, Table, view_header


class StockChecksView(ttk.Frame):
    def __init__(self, app, parent):
        super().__init__(parent)
        self.app, self.checks = app, {}
        self.flagged_only = tk.BooleanVar(value=True)
        view_header(self, "Stock count flags")
        self.metrics = Metrics(self, [("flagged", "Awaiting admin review"), ("corrected", "Corrected"), ("matched", "Matched counts")])
        self.metrics.pack(fill="x", pady=(0, 20))
        card = ttk.Frame(self, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(card, style="Card.TFrame")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ttk.Checkbutton(toolbar, text="Flagged counts only", variable=self.flagged_only, command=self.refresh, style="Card.TCheckbutton").pack(side="left")
        self.table = Table(card, [("id", "COUNT", 70, "w"), ("product", "PRODUCT", 190, "w"), ("expected", "RECORDED", 95, "e"), ("counted", "COUNTED", 90, "e"), ("difference", "DIFFERENCE", 100, "e"), ("status", "STATUS", 110, "w"), ("employee", "CHECKED BY", 150, "w"), ("date", "DATE", 180, "w")], empty="No stock count flags to review.")
        self.table.grid(row=1, column=0, sticky="nsew")
        self.table.tree.bind("<Double-1>", lambda _event: self.review())
        actions = ttk.Frame(card, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="e", pady=(15, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Review count", command=self.review, style="Primary.TButton").pack(side="left")
        self.after_idle(self.refresh)

    def refresh(self):
        actor, only, service = self.app.user.user_id, self.flagged_only.get(), self.app.service.stock

        def loaded(rows):
            visible = [row for row in rows if not only or row["status"] == "flagged"]
            self.checks = {row["check_id"]: row for row in visible}
            self.table.replace([(row["check_id"], (f"#{row['check_id']}", row["product_name"], row["expected_quantity"], row["counted_quantity"], f"{row['difference']:+,}", row["status"].capitalize(), row["checked_by_name"], row["checked_at"]), ("low",) if row["status"] == "flagged" else ()) for row in visible])
            self.metrics.set(**{status: sum(row["status"] == status for row in rows) for status in ("flagged", "corrected", "matched")})

        self.app.run_task(lambda: service.list_checks(actor), loaded, status="Loading stock counts…")

    def review(self):
        if self.app.busy:
            return
        check = self.checks.get(self.table.selected())
        if check is None:
            messagebox.showinfo("Select a count", "Select a stock count in the table first.", parent=self.app.root)
            return
        StockReviewDialog(self.app, check, self.refresh)

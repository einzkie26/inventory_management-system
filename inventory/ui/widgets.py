"""Reusable tables, metric cards, and modal windows."""

import tkinter as tk
from tkinter import ttk

from .theme import BG, INK, MUTED, WHITE, center_window


class Table(ttk.Frame):
    def __init__(self, parent, columns, *, empty="No records to display.", height=12):
        super().__init__(parent, style="Card.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(self, columns=[col[0] for col in columns], show="headings", selectmode="browse", height=height)
        for key, title, width, anchor in columns:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=min(width, 70), anchor=anchor, stretch=key not in {"id", "quantity", "price", "status"})
        vertical = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.empty = tk.Label(self.tree, text=empty, bg=WHITE, fg=MUTED, font=("Segoe UI", 11), wraplength=300)
        self.tree.tag_configure("low", foreground="#b45309")
        self.tree.tag_configure("archived", foreground="#94a3b8")
        self.replace([])

    def replace(self, rows) -> None:
        selection = self.selected()
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        for key, values, tags in rows:
            self.tree.insert("", "end", iid=str(key), values=values, tags=tags)
        if selection is not None and self.tree.exists(str(selection)):
            self.tree.selection_set(str(selection))
            self.tree.focus(str(selection))
        if self.tree.get_children():
            self.empty.place_forget()
        else:
            self.empty.place(relx=0.5, rely=0.5, anchor="center")

    def selected(self) -> int | None:
        selection = self.tree.selection()
        return int(selection[0]) if selection else None


class Metrics(ttk.Frame):
    def __init__(self, parent, labels):
        super().__init__(parent)
        self.values = {}
        for index, (key, title) in enumerate(labels):
            self.columnconfigure(index, weight=1, uniform="metrics")
            card = ttk.Frame(self, style="Card.TFrame", padding=(17, 15))
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 10, 0))
            ttk.Label(card, text=title, style="CardMuted.TLabel").pack(anchor="w")
            value = tk.StringVar(value="—")
            ttk.Label(card, textvariable=value, style="Metric.TLabel").pack(anchor="w", pady=(5, 0))
            self.values[key] = value

    def set(self, **values) -> None:
        for key, value in values.items():
            if key in self.values:
                self.values[key].set(str(value))


class Modal(tk.Toplevel):
    def __init__(self, app, title: str, width: int = 560, height: int = 550, on_close=None):
        super().__init__(app.root)
        self.app = app
        self.on_close = on_close
        self.title(title)
        self.configure(background=WHITE)
        self.transient(app.root)
        center_window(self, width, height)
        self.minsize(min(width, 480), min(height, 420))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.body = ttk.Frame(self, style="Card.TFrame", padding=24)
        self.body.pack(fill="both", expand=True)
        self.body.columnconfigure(0, weight=1)
        self.error = tk.StringVar()
        self.grab_set()

    def close(self) -> None:
        if self.app.busy:
            return
        self.grab_release()
        self.destroy()
        if self.on_close:
            self.on_close()

    def show_error(self, error: Exception) -> None:
        self.error.set(str(error))


def field(parent, title: str, variable, row: int, *, show="", column=0):
    ttk.Label(parent, text=title, style="Card.TLabel").grid(row=row, column=column, sticky="w", pady=(12, 5))
    entry = ttk.Entry(parent, textvariable=variable, show=show)
    entry.grid(row=row + 1, column=column, sticky="ew")
    return entry


def view_header(parent, title: str) -> None:
    ttk.Label(parent, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, 20))

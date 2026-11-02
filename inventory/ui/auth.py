"""Employee sign-in and first-admin setup inside the main window."""

import tkinter as tk
from tkinter import ttk

from .theme import BLUE, NAVY, TEAL, WHITE
from .widgets import field


class AuthView(ttk.Frame):
    def __init__(self, app, mode="login", username="", notice=""):
        super().__init__(app.container, style="Card.TFrame")
        self.app, self.mode = app, mode
        self.pack(fill="both", expand=True)
        self.columnconfigure(0, weight=1, uniform="auth")
        self.columnconfigure(1, weight=1, uniform="auth")
        self.rowconfigure(0, weight=1)
        hero = tk.Frame(self, bg=NAVY, padx=35, pady=35)
        hero.grid(row=0, column=0, sticky="nsew")
        tk.Label(hero, text="INVENTORY / MANAGER", bg=NAVY, fg=TEAL, font=("Segoe UI", 11, "bold")).pack(anchor="w")
        art = tk.Canvas(hero, bg=NAVY, highlightthickness=0, height=225, width=330)
        art.pack(fill="x", pady=(25, 0))
        for x, y, color in ((75, 70, TEAL), (170, 25, "#93c5fd"), (170, 127, "#818cf8")):
            art.create_polygon(x, y, x + 46, y - 23, x + 92, y, x + 46, y + 23, fill="", outline=color, width=2)
            art.create_line(x, y, x, y + 55, x + 46, y + 79, x + 92, y + 55, x + 92, y, fill=color, width=2)
            art.create_line(x + 46, y + 23, x + 46, y + 79, fill=color, width=2)
        tk.Label(hero, text="Everything in stock.\nEverything in view.", bg=NAVY, fg=WHITE, justify="left", font=("Segoe UI", 25, "bold")).pack(anchor="w", pady=(15, 18))
        tk.Label(hero, text="POWERED BY YOUR MYSQL DATABASE", bg=NAVY, fg="#8397b6", font=("Segoe UI", 9)).pack(side="bottom", anchor="w", pady=(20, 0))

        right = ttk.Frame(self, style="Card.TFrame", padding=(38, 24))
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        form = ttk.Frame(right, style="Card.TFrame")
        form.grid(row=1, column=0, sticky="ew")
        form.columnconfigure(0, weight=1)
        title = {
            "login": "Welcome back",
            "setup": "Set up your workspace",
        }[mode]
        ttk.Label(form, text=title, style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.username = tk.StringVar(value=username)
        self.email = tk.StringVar()
        self.password = tk.StringVar()
        self.confirm = tk.StringVar()
        self.error = tk.StringVar()
        row = 1
        first = field(form, "Username or email" if mode == "login" else "Username", self.username, row)
        row += 2
        if mode != "login":
            field(form, "Email address", self.email, row)
            row += 2
        self.password_entry = field(form, "Password", self.password, row, show="•")
        row += 2
        self.confirm_entry = None
        if mode != "login":
            self.confirm_entry = field(form, "Confirm password", self.confirm, row, show="•")
            row += 2
        self.visible = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="Show password", variable=self.visible, command=self.toggle_password, style="Card.TCheckbutton").grid(row=row, column=0, sticky="w", pady=(10, 0))
        row += 1
        if mode != "login":
            ttk.Label(form, text="8+ characters, uppercase and lowercase letters, a number, and a symbol.", style="CardMuted.TLabel", wraplength=365, font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=(9, 0))
            row += 1
        self.feedback = ttk.Label(form, textvariable=self.error, style="Error.TLabel", wraplength=370)
        self.feedback.grid(row=row, column=0, sticky="ew", pady=(10, 5))
        row += 1
        text = {"login": "Sign in", "setup": "Create workspace"}[mode]
        ttk.Button(form, text=text, command=self.submit, style="Primary.TButton").grid(row=row, column=0, sticky="ew", pady=(5, 10))
        row += 1
        if notice:
            self.error.set(notice)
            self.feedback.configure(style="Success.TLabel")
        for entry in (first, self.password_entry, self.confirm_entry):
            if entry is not None:
                entry.bind("<Return>", lambda _event: self.submit())
        self.after_idle(first.focus_set)

    def toggle_password(self) -> None:
        for entry in (self.password_entry, self.confirm_entry):
            if entry is not None:
                entry.configure(show="" if self.visible.get() else "•")

    def submit(self) -> None:
        if self.app.busy:
            return
        self.feedback.configure(style="Error.TLabel")
        self.error.set("")
        login, email, password = self.username.get(), self.email.get(), self.password.get()
        service = self.app.service
        if self.mode != "login" and password != self.confirm.get():
            self.error.set("The passwords do not match.")
            return
        if self.mode == "login":
            task = lambda: service.authenticate(login, password)
            success = self.app.start_session
        elif self.mode == "setup":
            task = lambda: service.setup_admin(login, email, password)
            success = self.app.start_session
        self.app.run_task(task, success, on_error=lambda exc: self.error.set(str(exc)), status="Signing in…" if self.mode == "login" else "Creating account…")

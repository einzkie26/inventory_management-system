"""Shared typography, spacing, and colors for all application screens."""

from tkinter import ttk

BG = "#f1f5f9"
WHITE = "#ffffff"
INK = "#0f172a"
MUTED = "#64748b"
BLUE = "#2563eb"
NAVY = "#101d35"
TEAL = "#5eead4"
RED = "#b91c1c"


def apply_theme(root) -> None:
    root.configure(background=BG)
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=BG, foreground=INK)
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=WHITE)
    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("Card.TLabel", background=WHITE)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("CardMuted.TLabel", background=WHITE, foreground=MUTED)
    style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"))
    style.configure("CardTitle.TLabel", background=WHITE, font=("Segoe UI", 22, "bold"))
    style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"))
    style.configure("CardHeading.TLabel", background=WHITE, font=("Segoe UI", 12, "bold"))
    style.configure("Metric.TLabel", background=WHITE, font=("Segoe UI", 21, "bold"))
    style.configure("Error.TLabel", background=WHITE, foreground=RED)
    style.configure("Success.TLabel", background=WHITE, foreground="#047857")
    style.configure("TEntry", fieldbackground="#f8fafc", bordercolor="#cbd5e1", padding=(10, 9))
    style.map("TEntry", bordercolor=[("focus", BLUE)])
    style.configure("TSpinbox", fieldbackground="#f8fafc", padding=(7, 8), arrowsize=14)
    style.configure("TButton", background=WHITE, foreground=INK, borderwidth=1, bordercolor="#cbd5e1", padding=(13, 9))
    style.map("TButton", background=[("active", "#e2e8f0"), ("disabled", "#e2e8f0")], foreground=[("disabled", "#94a3b8")])
    style.configure("Primary.TButton", background=BLUE, foreground=WHITE, borderwidth=0, padding=(16, 10), font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton", background=[("disabled", "#94a3b8"), ("active", "#1d4ed8")], foreground=[("disabled", WHITE)])
    style.configure("Danger.TButton", foreground=RED)
    style.configure("Link.TButton", background=WHITE, foreground=BLUE, borderwidth=0, padding=(3, 7))
    style.map("Link.TButton", background=[("active", "#eff6ff")])
    style.configure("Card.TCheckbutton", background=WHITE)
    style.map("Card.TCheckbutton", background=[("active", WHITE)])
    style.configure("Treeview", background=WHITE, fieldbackground=WHITE, foreground=INK, rowheight=35, borderwidth=0)
    style.configure("Treeview.Heading", background="#e9eff6", foreground=MUTED, font=("Segoe UI", 9, "bold"), padding=(9, 11), borderwidth=0)
    style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#1e3a8a")])
    style.configure("Vertical.TScrollbar", background="#cbd5e1", troughcolor=WHITE, borderwidth=0, arrowsize=12)
    style.configure("Horizontal.TScrollbar", background="#cbd5e1", troughcolor=WHITE, borderwidth=0, arrowsize=12)
    style.configure("Sidebar.TFrame", background=NAVY)
    style.configure("Sidebar.TLabel", background=NAVY, foreground=WHITE)
    style.configure("SidebarMuted.TLabel", background=NAVY, foreground="#a8b8d0")
    style.configure("SidebarBrand.TLabel", background=NAVY, foreground=WHITE, font=("Segoe UI", 19, "bold"))
    style.configure("Nav.TButton", background=NAVY, foreground="#b6c5dc", borderwidth=0, anchor="w", padding=(18, 13))
    style.map("Nav.TButton", background=[("active", "#1b2d4a")])
    style.configure("SelectedNav.TButton", background="#253c60", foreground=WHITE, borderwidth=0, anchor="w", padding=(18, 13), font=("Segoe UI", 10, "bold"))
    style.map("SelectedNav.TButton", background=[("active", "#304c75")])
    style.configure("TProgressbar", background=BLUE, troughcolor=BG, borderwidth=0, thickness=3)


def center_window(window, width: int, height: int) -> None:
    width = min(width, window.winfo_screenwidth() - 70)
    height = min(height, window.winfo_screenheight() - 100)
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2 - 20)
    window.geometry(f"{width}x{height}+{x}+{y}")

"""Entry point and background task runner. All Tk calls stay on the main thread."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import gc
import logging
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from .audio import play_sound
from .backup import backup_database
from .config import PROJECT_ROOT
from .db import Database
from .errors import InventoryError
from .receipts import export_receipt
from .services import InventoryService
from .ui.auth import AuthView
from .ui.dialogs import OrderDialog
from .ui.shell import Shell
from .ui.theme import apply_theme, center_window

logger = logging.getLogger(__name__)


class InventoryApp:
    def __init__(self, root=None, database=None, *, auto_initialize=True):
        self.root = root if root is not None else tk.Tk()
        self.reload_config = database is None
        self.database = database if database is not None else Database()
        self.settings, self.service = self.database.settings, InventoryService(self.database)
        self.user, self.view = None, None
        self.busy, self.closed = False, False
        self._restore_gc = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inventory-db")
        self.root.title("Inventory Management System")
        apply_theme(self.root)
        center_window(self.root, 1280, 790)
        self.root.minsize(1040, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.report_callback_exception = self.report_callback_exception
        status_bar = ttk.Frame(self.root, padding=(14, 6))
        status_bar.pack(side="bottom", fill="x")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(status_bar, textvariable=self.status, style="Muted.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(status_bar, mode="indeterminate", length=110)
        self.container = ttk.Frame(self.root)
        self.container.pack(fill="both", expand=True)
        if auto_initialize:
            self.initialize()

    def clear(self):
        for child in self.container.winfo_children():
            child.destroy()

    def initialize(self):
        if self.busy:
            return
        self.clear()
        boot = ttk.Frame(self.container, padding=35)
        boot.pack(expand=True)
        ttk.Label(boot, text="Opening your workspace", style="Title.TLabel").pack(anchor="w")
        detail = ttk.Label(boot, text="Connecting to your MySQL database…", style="Muted.TLabel", wraplength=650)
        detail.pack(anchor="w", pady=(12, 20))

        def prepare_config():
            if self.reload_config:
                self.database = Database()
                self.settings = self.database.settings
                self.service = InventoryService(self.database)

        def failed(error):
            detail.configure(text=str(error))
            ttk.Label(boot, text="Connection settings are in .env at the project root.", style="Muted.TLabel").pack(anchor="w", pady=(0, 15))
            ttk.Button(boot, text="Retry connection", command=self.initialize, style="Primary.TButton").pack(anchor="w")

        try:
            prepare_config()
        except InventoryError as exc:
            failed(exc)
            return
        database = self.database

        def task():
            database.initialize()

        self.run_task(task, lambda _result: self.show_auth(), on_error=failed, status="Connecting to MySQL…")

    def set_status(self, message):
        self.status.set(message)

    def run_task(self, task, on_success=None, *, on_error=None, status="Working…"):
        if self.busy or self.closed:
            return False
        self.busy = True
        self.root.configure(cursor="watch")
        self.progress.pack(side="right")
        self.progress.start(12)
        self.set_status(status)
        # Cyclic collection can finalize Tk variables on whichever thread triggers it.
        # Collect on the UI thread, and postpone automatic collection until this job ends.
        self._restore_gc = gc.isenabled()
        gc.disable()
        gc.collect()
        future = self.executor.submit(task)

        def poll():
            if self.closed:
                return
            if not future.done():
                self.root.after(35, poll)
                return
            self.busy = False
            self.root.configure(cursor="")
            self.progress.stop()
            self.progress.pack_forget()
            gc.collect()
            if self._restore_gc:
                gc.enable()
            self._restore_gc = False
            try:
                result = future.result()
            except Exception as exc:
                if isinstance(exc, InventoryError):
                    error = exc
                elif isinstance(exc, OSError):
                    logger.exception("Local file operation failed")
                    error = InventoryError("Could not read or write a local file. Check the configured folder and disk space. Saved orders are unaffected.")
                else:
                    logger.exception("Background task failed")
                    error = InventoryError("The operation could not be completed. See inventory.log for details.")
                self.set_status(str(error))
                play_sound("error.wav", enabled=self.settings.sound)
                if on_error:
                    on_error(error)
                else:
                    messagebox.showerror("Unable to complete action", str(error), parent=self.root)
            else:
                self.set_status("Ready")
                if on_success:
                    on_success(result)

        self.root.after(35, poll)
        return True

    def show_auth(self, mode="login", **kwargs):
        if self.busy:
            return
        self.clear()
        self.user = None
        self.view = AuthView(self, mode, **kwargs)

    def start_session(self, user):
        self.clear()
        play_sound("bell1.wav", enabled=self.settings.sound)
        self.user = user
        self.view = Shell(self)
        self.set_status(f"Signed in as {user.username}.")

    def logout(self):
        if self.busy:
            return
        self.show_auth()
        self.set_status("Signed out.")

    def show_order(self, order_id, *, auto_export=False):
        actor = self.user.user_id
        service, directory = self.service, self.settings.receipt_dir

        def task():
            order = service.sales.order_detail(actor, order_id)
            path, error = None, None
            if auto_export:
                try:
                    path = export_receipt(order, directory)
                except OSError as exc:
                    logger.exception("Order saved but receipt export failed")
                    error = exc
            return order, path, error

        self.run_task(task, lambda result: OrderDialog(self, *result), status=f"Loading order #{order_id}…")

    def report_callback_exception(self, exc_type, value, traceback):
        logger.error("UI callback failed", exc_info=(exc_type, value, traceback))
        messagebox.showerror("Application error", "This action could not be completed. See inventory.log for details.", parent=self.root)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.root.withdraw()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.root.destroy()
        gc.collect()
        if self._restore_gc:
            gc.enable()
        self._restore_gc = False

    def run(self):
        self.root.mainloop()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Inventory Management System — MySQL / XAMPP")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--init-db", action="store_true", help="Create or upgrade the configured schema without opening the GUI")
    actions.add_argument("--check-db", action="store_true", help="Check the database connection without changing records")
    actions.add_argument("--backup", action="store_true", help="Save a SQL backup of the configured database")
    args = parser.parse_args(argv)
    logging.basicConfig(filename=PROJECT_ROOT / "inventory.log", encoding="utf-8", level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        database = Database()
        if args.init_db:
            database.initialize()
            print(f"Database '{database.settings.database}' is ready.")
            return 0
        if args.check_db:
            with database.transaction() as cursor:
                cursor.execute("SELECT VERSION() AS version")
                print(f"Connected to {database.settings.database} at {database.settings.host}:{database.settings.port} ({cursor.fetchone()['version']}).")
            return 0
        if args.backup:
            print(f"Backup saved: {backup_database(database)}")
            return 0
        application = InventoryApp(database=database)
        application.reload_config = True
        application.run()
        return 0
    except InventoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

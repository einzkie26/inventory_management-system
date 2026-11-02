"""Short-lived MySQL connections and transaction boundaries, without UI imports."""

from contextlib import contextmanager
from typing import Iterator

from .config import Settings
from .errors import DatabaseError, ValidationError

try:
    import mysql.connector as connector
except ImportError:
    connector = None


class Database:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()

    def connect(self, *, server_only: bool = False):
        if connector is None:
            raise DatabaseError("The MySQL driver is missing. Run: python -m pip install -r requirements.txt")
        options = dict(
            host=self.settings.host, port=self.settings.port,
            user=self.settings.user, password=self.settings.password,
            charset="utf8mb4", collation="utf8mb4_unicode_ci",
            connection_timeout=5, autocommit=False, use_pure=True,
            time_zone=self.settings.time_zone,
        )
        if not server_only:
            options["database"] = self.settings.database
        try:
            return connector.connect(**options)
        except connector.Error as exc:
            raise DatabaseError(
                f"Cannot connect to MySQL at {self.settings.host}:{self.settings.port}. "
                "Start MySQL in XAMPP and check DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, and DB_NAME in .env. "
                f"(MySQL error {exc.errno})"
            ) from exc

    @contextmanager
    def transaction(self) -> Iterator:
        connection = self.connect()
        cursor = None
        try:
            connection.start_transaction()
            cursor = connection.cursor(dictionary=True, buffered=True)
            yield cursor
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if connector is not None and isinstance(exc, connector.IntegrityError):
                if exc.errno == 1062:
                    raise ValidationError("That username or email address is already in use.") from exc
                raise DatabaseError("The change conflicts with related database records.") from exc
            if connector is not None and isinstance(exc, connector.Error):
                raise DatabaseError(f"MySQL could not complete the operation (error {exc.errno}). Please refresh and try again.") from exc
            raise
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def initialize(self) -> None:
        from .migrations import initialize
        initialize(self)

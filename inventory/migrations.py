"""Idempotent schema setup and upgrades from the original four-table application."""

import hashlib
import logging
from pathlib import Path

from .backup import backup_database, quote_identifier
from .bootstrap import ensure_default_admin
from .db import connector
from .errors import DatabaseError
from .security import ALGORITHM, hash_password

SCHEMA_VERSION = 2
logger = logging.getLogger(__name__)


def _columns(cursor, table: str) -> dict:
    cursor.execute(f"SHOW COLUMNS FROM {quote_identifier(table)}")
    return {row["Field"]: row for row in cursor.fetchall()}


def _add_columns(cursor, table: str, definitions: dict[str, str]) -> None:
    existing = _columns(cursor, table)
    for name, definition in definitions.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE {quote_identifier(table)} ADD COLUMN {quote_identifier(name)} {definition}")


def _index(cursor, table: str, name: str, columns: str, *, unique: bool = False) -> None:
    cursor.execute(f"SHOW INDEX FROM {quote_identifier(table)}")
    if any(row["Key_name"] == name for row in cursor.fetchall()):
        return
    prefix = "UNIQUE " if unique else ""
    try:
        cursor.execute(f"CREATE {prefix}INDEX {quote_identifier(name)} ON {quote_identifier(table)} ({columns})")
    except connector.IntegrityError as exc:
        raise DatabaseError(
            f"Existing {table} records contain duplicate values for {columns}. "
            "Reconcile these duplicates in MySQL, then restart. A backup was saved before the upgrade."
        ) from exc


def _foreign_key(cursor, schema: str, table: str, column: str, parent: str, parent_column: str) -> None:
    cursor.execute(
        "SELECT k.CONSTRAINT_NAME,r.DELETE_RULE FROM information_schema.KEY_COLUMN_USAGE k "
        "JOIN information_schema.REFERENTIAL_CONSTRAINTS r ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA "
        "AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME AND r.TABLE_NAME=k.TABLE_NAME "
        "WHERE k.TABLE_SCHEMA=%s AND k.TABLE_NAME=%s AND k.COLUMN_NAME=%s AND k.REFERENCED_TABLE_NAME=%s",
        (schema, table, column, parent),
    )
    existing = cursor.fetchall()
    if existing and all(row["DELETE_RULE"] in {"RESTRICT", "NO ACTION"} for row in existing):
        return
    for row in existing:
        cursor.execute(f"ALTER TABLE {quote_identifier(table)} DROP FOREIGN KEY {quote_identifier(row['CONSTRAINT_NAME'])}")
    name = quote_identifier(f"fk_{table}_{column}")
    cursor.execute(
        f"ALTER TABLE {quote_identifier(table)} ADD CONSTRAINT {name} "
        f"FOREIGN KEY ({quote_identifier(column)}) REFERENCES {quote_identifier(parent)} "
        f"({quote_identifier(parent_column)}) ON DELETE RESTRICT"
    )


def _upgrade_legacy(cursor, schema: str) -> None:
    # Preserve identifiers, balances, stock, order totals, and the original line-total 'price' column.
    for table in ("users", "products", "orders", "order_details"):
        cursor.execute(
            "SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
            (schema, table),
        )
        if cursor.fetchone()["ENGINE"].upper() != "INNODB":
            cursor.execute(f"ALTER TABLE {quote_identifier(table)} ENGINE=InnoDB")
        cursor.execute(f"ALTER TABLE {quote_identifier(table)} CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")

    _add_columns(cursor, "users", {
        "balance": "DECIMAL(13,2) NOT NULL DEFAULT 0.00",
        "created_at": "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP",
    })
    cursor.execute("ALTER TABLE users MODIFY password VARCHAR(255) NOT NULL, MODIFY email VARCHAR(254) NOT NULL, MODIFY balance DECIMAL(13,2) NOT NULL DEFAULT 0.00")
    _add_columns(cursor, "products", {
        "active": "TINYINT(1) NOT NULL DEFAULT 1",
        "version": "INT NOT NULL DEFAULT 1",
    })
    cursor.execute("UPDATE products SET description='' WHERE description IS NULL")
    cursor.execute("UPDATE products SET category='Uncategorized' WHERE category IS NULL OR TRIM(category)=''")
    cursor.execute("ALTER TABLE products MODIFY description TEXT NOT NULL, MODIFY price DECIMAL(13,2) NOT NULL, MODIFY category VARCHAR(80) NOT NULL")

    _add_columns(cursor, "orders", {"username": "VARCHAR(255) NULL"})
    cursor.execute("UPDATE orders o JOIN users u ON u.user_id=o.user_id SET o.username=u.username WHERE o.username IS NULL")
    cursor.execute("ALTER TABLE orders MODIFY username VARCHAR(255) NOT NULL, MODIFY total_price DECIMAL(13,2) NOT NULL")
    _add_columns(cursor, "order_details", {
        "product_name": "VARCHAR(200) NULL", "category": "VARCHAR(80) NULL",
        "unit_price": "DECIMAL(13,2) NULL",
    })
    cursor.execute(
        "UPDATE order_details d JOIN products p ON p.product_id=d.product_id "
        "SET d.product_name=COALESCE(d.product_name,p.name), d.category=COALESCE(d.category,p.category)"
    )
    cursor.execute("UPDATE order_details SET unit_price=ROUND(price/quantity,2) WHERE unit_price IS NULL AND quantity>0")
    cursor.execute(
        "ALTER TABLE order_details MODIFY product_name VARCHAR(200) NOT NULL, MODIFY category VARCHAR(80) NOT NULL, "
        "MODIFY unit_price DECIMAL(13,2) NOT NULL, MODIFY price DECIMAL(13,2) NOT NULL"
    )

    _index(cursor, "users", "uq_users_username", "username", unique=True)
    _index(cursor, "users", "uq_users_email", "email", unique=True)
    _index(cursor, "products", "ix_products_active_category", "active, category")
    _index(cursor, "orders", "ix_orders_user_date", "user_id, order_date")
    _index(cursor, "order_details", "ix_details_order", "order_id")
    _index(cursor, "balance_transactions", "ix_balance_user_date", "user_id, created_at")
    _index(cursor, "stock_movements", "ix_stock_product_date", "product_id, created_at")

    for table, column, parent, parent_column in (
        ("orders", "user_id", "users", "user_id"),
        ("order_details", "order_id", "orders", "order_id"),
        ("order_details", "product_id", "products", "product_id"),
        ("balance_transactions", "user_id", "users", "user_id"),
        ("balance_transactions", "created_by", "users", "user_id"),
        ("balance_transactions", "order_id", "orders", "order_id"),
        ("stock_movements", "product_id", "products", "product_id"),
        ("stock_movements", "created_by", "users", "user_id"),
        ("stock_movements", "order_id", "orders", "order_id"),
    ):
        _foreign_key(cursor, schema, table, column, parent, parent_column)

    for table, name, expression in (
        ("users", "chk_users_role", "role IN ('admin','customer')"),
        ("users", "chk_users_balance", "balance >= 0"),
        ("products", "chk_products_quantity", "quantity >= 0"),
        ("products", "chk_products_price", "price >= 0"),
        ("orders", "chk_orders_total", "total_price >= 0"),
        ("order_details", "chk_details_quantity", "quantity > 0"),
        ("order_details", "chk_details_prices", "unit_price >= 0 AND price >= 0"),
    ):
        cursor.execute(
            "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME=%s",
            (schema, table, name),
        )
        if not cursor.fetchone():
            cursor.execute(f"ALTER TABLE {quote_identifier(table)} ADD CONSTRAINT {quote_identifier(name)} CHECK ({expression})")

    cursor.execute("SELECT user_id,password FROM users")
    for row in cursor.fetchall():
        if not row["password"].startswith(ALGORITHM + "$"):
            cursor.execute("UPDATE users SET password=%s WHERE user_id=%s", (hash_password(row["password"]), row["user_id"]))

    cursor.execute(
        "INSERT INTO balance_transactions (user_id,amount,reason,created_by) "
        "SELECT u.user_id,u.balance,'Opening balance from legacy database',u.user_id FROM users u "
        "WHERE u.balance<>0 AND NOT EXISTS (SELECT 1 FROM balance_transactions b WHERE b.user_id=u.user_id)"
    )
    cursor.execute("INSERT IGNORE INTO app_state (state_id,description) VALUES (1,'First administrator setup lock')")


def _drop_check(cursor, schema: str, table: str, name: str) -> None:
    cursor.execute(
        "SELECT CONSTRAINT_NAME FROM information_schema.TABLE_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME=%s AND CONSTRAINT_TYPE='CHECK'",
        (schema, table, name),
    )
    if not cursor.fetchone():
        return
    cursor.execute("SELECT VERSION() AS version")
    operation = "DROP CONSTRAINT" if "MariaDB" in cursor.fetchone()["version"] else "DROP CHECK"
    cursor.execute(f"ALTER TABLE {quote_identifier(table)} {operation} {quote_identifier(name)}")


def _upgrade_workforce(cursor, schema: str) -> None:
    _drop_check(cursor, schema, "users", "chk_users_role")
    cursor.execute("ALTER TABLE users MODIFY role VARCHAR(32) NOT NULL DEFAULT 'inventory_worker'")
    _add_columns(cursor, "users", {"active": "TINYINT(1) NOT NULL DEFAULT 1"})
    cursor.execute("UPDATE users SET role='inventory_worker' WHERE role='customer'")
    cursor.execute(
        "ALTER TABLE users ADD CONSTRAINT chk_users_role "
        "CHECK (role IN ('inventory_worker','stock_checker','delivery_assistant','admin'))"
    )
    _add_columns(cursor, "orders", {
        "recipient": "VARCHAR(200) NOT NULL DEFAULT ''",
        "destination": "VARCHAR(255) NOT NULL DEFAULT ''",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'completed'",
        "completed_at": "DATETIME NULL",
    })
    cursor.execute("UPDATE orders SET recipient=LEFT(username,200) WHERE recipient=''")
    cursor.execute("UPDATE orders SET completed_at=order_date WHERE status='completed' AND completed_at IS NULL")
    _drop_check(cursor, schema, "orders", "chk_order_status")
    cursor.execute(
        "ALTER TABLE orders ADD CONSTRAINT chk_order_status "
        "CHECK (status IN ('pending_delivery','in_transit','completed','cancelled'))"
    )
    for statement in Path(__file__).with_name("workforce.sql").read_text(encoding="utf-8").split(";"):
        if statement.strip():
            cursor.execute(statement)
    _index(cursor, "users", "ix_users_role_active", "role,active")
    _index(cursor, "orders", "ix_orders_status_date", "status,order_date")


def initialize(database) -> None:
    server = database.connect(server_only=True)
    try:
        cursor = server.cursor()
        try:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {quote_identifier(database.settings.database)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        finally:
            cursor.close()
    except connector.Error as exc:
        raise DatabaseError(f"Cannot create the configured database (MySQL error {exc.errno}). Check database permissions.") from exc
    finally:
        server.close()

    connection = database.connect()
    cursor = connection.cursor(dictionary=True, buffered=True)
    lock = "inventory_schema_" + hashlib.sha256(database.settings.database.encode()).hexdigest()[:40]
    locked = False
    try:
        cursor.execute("SELECT GET_LOCK(%s,10) AS acquired", (lock,))
        locked = cursor.fetchone()["acquired"] == 1
        if not locked:
            raise DatabaseError("Another application is updating the database schema. Try again shortly.")
        cursor.execute("SHOW TABLES")
        tables = {next(iter(row.values())) for row in cursor.fetchall()}
        version = 0
        if "schema_migrations" in tables:
            cursor.execute("SELECT COALESCE(MAX(version),0) AS version FROM schema_migrations")
            version = cursor.fetchone()["version"]
        if version > SCHEMA_VERSION:
            raise DatabaseError("This database was created by a newer application. Update this application before continuing.")
        if tables and version < SCHEMA_VERSION:
            backup_path = backup_database(database)
            logger.info("Saved pre-upgrade backup to %s", backup_path)
        if version < 1:
            for statement in Path(__file__).with_name("schema.sql").read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    cursor.execute(statement)
            _upgrade_legacy(cursor, database.settings.database)
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (1)")
            connection.commit()
        if version < 2:
            _upgrade_workforce(cursor, database.settings.database)
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (2)")
            connection.commit()
        ensure_default_admin(cursor)
        connection.commit()
    except connector.Error as exc:
        connection.rollback()
        logger.exception("Schema initialization failed")
        raise DatabaseError(
            f"The database schema could not be upgraded (MySQL error {exc.errno}). "
            "No records were deleted. Check inventory.log and the pre-upgrade SQL backup in backups/."
        ) from exc
    finally:
        if locked:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (lock,))
            cursor.fetchone()
        cursor.close()
        connection.close()

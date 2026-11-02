"""Portable SQL backups. Restoring requires an empty, explicitly chosen database."""

from datetime import date, datetime, time
from decimal import Decimal
import math
from pathlib import Path


def _literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, (datetime, date, time)):
        return "'" + value.isoformat() + "'"
    if isinstance(value, bytes):
        return "0x" + value.hex() if value else "''"
    encoded = str(value).encode("utf-8").hex()
    return "_utf8mb4 0x" + encoded if encoded else "''"


def quote_identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def backup_database(database, directory: Path | None = None) -> Path:
    directory = directory or database.settings.backup_dir
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{database.settings.database}_{datetime.now():%Y%m%d_%H%M%S_%f}.sql"
    path = directory / filename
    connection = database.connect()
    cursor = None
    try:
        connection.start_transaction(consistent_snapshot=True)
        cursor = connection.cursor(buffered=True)
        cursor.execute("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")
        tables = [row[0] for row in cursor.fetchall()]
        with path.open("x", encoding="utf-8", newline="\n") as output:
            output.write("-- Inventory backup. Restore into an EMPTY database. Contains account data.\n")
            output.write("SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS=0;\nSET SQL_MODE='NO_AUTO_VALUE_ON_ZERO';\n")
            for table in tables:
                name = quote_identifier(table)
                cursor.execute(f"SHOW CREATE TABLE {name}")
                output.write(cursor.fetchone()[1] + ";\n")
                cursor.execute(f"SELECT * FROM {name}")
                columns = ", ".join(quote_identifier(column[0]) for column in cursor.description)
                for row in cursor:
                    values = ", ".join(_literal(value) for value in row)
                    output.write(f"INSERT INTO {name} ({columns}) VALUES ({values});\n")
            output.write("SET FOREIGN_KEY_CHECKS=1;\n")
        connection.commit()
        return path
    except Exception:
        connection.rollback()
        if path.exists():
            path.unlink()
        raise
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

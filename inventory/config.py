"""Configuration anchored to the project, independent of the working directory."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from .errors import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path = PROJECT_ROOT / ".env") -> dict[str, str]:
    """Read simple KEY=value settings without modifying the process environment."""
    values = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            values[key] = value
    return values


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "root"
    password: str = field(default="", repr=False)
    database: str = "inventory_management"
    receipt_dir: Path = PROJECT_ROOT / "receipts"
    backup_dir: Path = PROJECT_ROOT / "backups"
    sound: bool = False
    time_zone: str = "+08:00"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", self.database):
            raise ValidationError("DB_NAME must contain only letters, numbers, and underscores (up to 64 characters).")
        if not 1 <= self.port <= 65535:
            raise ValidationError("DB_PORT must be between 1 and 65535.")
        if not re.fullmatch(r"[+-](?:0\d|1[0-3]):[0-5]\d|[+]14:00", self.time_zone):
            raise ValidationError("DB_TIME_ZONE must be a UTC offset such as +08:00.")

    @classmethod
    def from_env(cls) -> "Settings":
        values = load_env()

        def setting(name: str, default: str) -> str:
            return os.environ.get(name, values.get(name, default))

        try:
            port = int(setting("DB_PORT", "3306"))
        except ValueError as exc:
            raise ValidationError("DB_PORT must be a number.") from exc

        def local_path(name: str, default: str) -> Path:
            path = Path(setting(name, default)).expanduser()
            return path if path.is_absolute() else PROJECT_ROOT / path

        return cls(
            host=setting("DB_HOST", "127.0.0.1"),
            port=port,
            user=setting("DB_USER", "root"),
            password=setting("DB_PASSWORD", ""),
            database=setting("DB_NAME", "inventory_management"),
            receipt_dir=local_path("RECEIPT_DIR", "receipts"),
            backup_dir=local_path("BACKUP_DIR", "backups"),
            sound=setting("INVENTORY_SOUND", "0").lower() in {"1", "true", "yes"},
            time_zone=setting("DB_TIME_ZONE", "+08:00"),
        )

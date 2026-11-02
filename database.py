"""Compatibility import for callers of the original database helper."""

from inventory.config import Settings
from inventory.db import Database

__all__ = ["Database", "Settings", "connect_to_database"]


def connect_to_database():
    """Return a live MySQL connection; errors are explicit and have no UI side effects."""
    return Database().connect()

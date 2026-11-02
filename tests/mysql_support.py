"""Fixtures may only create, clear, and drop randomly named inventory_test_* databases."""

from dataclasses import replace
import os
from pathlib import Path
import re
import tempfile
import unittest
import uuid

from inventory.backup import quote_identifier
from inventory.config import Settings
from inventory.db import Database


class MySQLTestCase(unittest.TestCase):
    def setUp(self):
        if os.getenv("INVENTORY_TEST_MYSQL") != "1":
            self.skipTest("Set INVENTORY_TEST_MYSQL=1 to run against isolated MySQL test databases.")
        self.temp = tempfile.TemporaryDirectory(prefix="inventory-tests-")
        self.addCleanup(self.temp.cleanup)
        self.schema = "inventory_test_" + uuid.uuid4().hex[:12]
        settings = replace(Settings.from_env(), database=self.schema, receipt_dir=Path(self.temp.name) / "receipts", backup_dir=Path(self.temp.name) / "backups", sound=False)
        self.db = Database(settings)
        connection = self.db.connect(server_only=True)
        try:
            cursor = connection.cursor()
            cursor.execute(f"CREATE DATABASE {quote_identifier(self.schema)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.close()
        finally:
            connection.close()
        self.addCleanup(self.drop_test_schema, self.schema)

    def drop_test_schema(self, schema):
        if not re.fullmatch(r"inventory_test_[a-f0-9]{12}", schema):
            raise AssertionError("Refusing to drop a non-test database")
        connection = self.db.connect(server_only=True)
        try:
            cursor = connection.cursor()
            cursor.execute(f"DROP DATABASE IF EXISTS {quote_identifier(schema)}")
            cursor.close()
        finally:
            connection.close()

    def scalar(self, query, params=()):
        with self.db.transaction() as cursor:
            cursor.execute(query, params)
            return next(iter(cursor.fetchone().values()))

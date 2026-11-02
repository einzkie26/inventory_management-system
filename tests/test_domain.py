from dataclasses import replace
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from inventory.config import PROJECT_ROOT, Settings, load_env
from inventory.errors import ValidationError
from inventory.models import Manifest, Product, currency, money, quantity
from inventory.security import hash_password, verify_password


class DomainTests(unittest.TestCase):
    def test_money_rejects_invalid_precision_and_nonfinite_values(self):
        for value in ("-1", "NaN", "Infinity", "0.001", "hello", "", "100000000000", None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                money(value)
        self.assertEqual(money("12.30"), Decimal("12.30"))
        self.assertEqual(currency(Decimal("1234.5")), "$1,234.50")

    def test_positive_credit_and_integer_stock(self):
        with self.assertRaises(ValidationError):
            money("0", positive=True)
        for value in ("-1", "1.5", "NaN", "2147483648", "1e2", True):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                quantity(value)
        self.assertEqual(quantity("0"), 0)
        with self.assertRaises(ValidationError):
            quantity("0", allow_zero=False)

    def test_duplicate_manifest_lines_merge_and_cannot_exceed_stock(self):
        product = Product(1, "Pen", "", 5, Decimal("0.10"), "Stationery")
        cart = Manifest()
        cart.add(product, 2)
        cart.add(product, 3)
        self.assertEqual(len(cart.items), 1)
        self.assertEqual(cart.items[0].quantity, 5)
        self.assertEqual(cart.total, Decimal("0.50"))
        with self.assertRaises(ValidationError):
            cart.add(product, 1)
        self.assertEqual(cart.items[0].quantity, 5)
        cart.remove(1)
        self.assertEqual(cart.total, Decimal("0.00"))

    def test_manifest_requires_refresh_for_changed_price_and_archived_products(self):
        product = Product(1, "Pen", "", 10, Decimal("1.00"), "Stationery")
        cart = Manifest()
        cart.add(product, 1)
        with self.assertRaises(ValidationError):
            cart.add(replace(product, price=Decimal("2.00")), 1)
        with self.assertRaises(ValidationError):
            Manifest().add(replace(product, active=False), 1)

    def test_manifest_excludes_stock_reserved_for_other_deliveries(self):
        product = Product(1, "Pen", "", 10, Decimal("1.00"), "Stationery", reserved=7)
        manifest = Manifest()
        self.assertEqual(product.available, 3)
        with self.assertRaises(ValidationError):
            manifest.add(product, 4)
        manifest.add(product, 3)
        self.assertEqual(manifest.total, Decimal("3.00"))

    def test_password_hashes_are_salted_and_invalid_hashes_fail_closed(self):
        first, second = hash_password("Secret123!"), hash_password("Secret123!")
        self.assertNotEqual(first, second)
        self.assertNotIn("Secret123!", first)
        self.assertEqual(verify_password("Secret123!", first), (True, False))
        self.assertEqual(verify_password("wrong", first), (False, False))
        self.assertEqual(verify_password("old-password", "old-password"), (True, True))
        self.assertEqual(verify_password("anything", "pbkdf2_sha256$bad$broken"), (False, False))

    def test_configuration_does_not_expose_password_or_depend_on_cwd(self):
        settings = Settings(password="private-value")
        self.assertNotIn("private-value", repr(settings))
        with self.assertRaises(ValidationError):
            Settings(database="unsafe`name")
        with self.assertRaises(ValidationError):
            Settings(port=0)
        with self.assertRaises(ValidationError):
            Settings(time_zone="system")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# Settings\nDB_PASSWORD='a=b#c'\nDB_PORT=3307\n", encoding="utf-8")
            self.assertEqual(load_env(path)["DB_PASSWORD"], "a=b#c")
            with patch("inventory.config.load_env", return_value=load_env(path)), patch.dict(os.environ, {"DB_PORT": "3308", "RECEIPT_DIR": "custom-receipts"}):
                loaded = Settings.from_env()
                self.assertEqual(loaded.port, 3308)
                self.assertEqual(loaded.receipt_dir, PROJECT_ROOT / "custom-receipts")


if __name__ == "__main__":
    unittest.main()

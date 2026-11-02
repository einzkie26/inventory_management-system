"""Default admin creation, safe restart behavior, and concurrent initialization."""

from concurrent.futures import ThreadPoolExecutor

from inventory.errors import AuthenticationError, DatabaseError
from inventory.security import hash_password
from inventory.services import InventoryService

from .mysql_support import MySQLTestCase


class DefaultAdminTests(MySQLTestCase):
    def test_fresh_database_automatically_creates_the_requested_login(self):
        self.db.initialize()
        service = InventoryService(self.db)
        admin = service.authenticate("admin", "Admin1234!")
        self.assertEqual(admin.role, "admin")
        self.assertTrue(admin.active)
        self.assertFalse(service.needs_setup())
        stored = self.scalar("SELECT password FROM users WHERE user_id=%s", (admin.user_id,))
        self.assertNotEqual(stored, "Admin1234!")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))

    def test_restarting_preserves_account_id_and_a_changed_password(self):
        self.db.initialize()
        service = InventoryService(self.db)
        admin = service.authenticate("admin", "Admin1234!")
        changed_hash = hash_password("ChangedPassword123!")
        with self.db.transaction() as cursor:
            cursor.execute("UPDATE users SET password=%s WHERE user_id=%s", (changed_hash, admin.user_id))
        self.db.initialize()
        self.db.initialize()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE role='admin'"), 1)
        self.assertEqual(service.authenticate("admin", "ChangedPassword123!").user_id, admin.user_id)
        self.assertEqual(self.scalar("SELECT password FROM users WHERE user_id=%s", (admin.user_id,)), changed_hash)
        with self.assertRaises(AuthenticationError):
            service.authenticate("admin", "Admin1234!")

    def test_existing_custom_admin_does_not_get_an_extra_default_account(self):
        self.db.initialize()
        with self.db.transaction() as cursor:
            cursor.execute("UPDATE users SET username='customadmin' WHERE username='admin'")
        self.db.initialize()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE username='admin'"), 0)
        self.assertEqual(InventoryService(self.db).authenticate("customadmin", "Admin1234!").role, "admin")

    def test_disabled_admin_is_not_automatically_reactivated(self):
        self.db.initialize()
        with self.db.transaction() as cursor:
            cursor.execute("UPDATE users SET active=0 WHERE username='admin'")
        self.db.initialize()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE role='admin'"), 1)
        self.assertEqual(self.scalar("SELECT active FROM users WHERE username='admin'"), 0)
        with self.assertRaises(AuthenticationError):
            InventoryService(self.db).authenticate("admin", "Admin1234!")

    def test_existing_employee_named_admin_is_not_promoted(self):
        self.db.initialize()
        with self.db.transaction() as cursor:
            cursor.execute("UPDATE users SET role='inventory_worker' WHERE username='admin'")
        with self.assertRaisesRegex(DatabaseError, "belongs to another employee"):
            self.db.initialize()
        self.assertEqual(self.scalar("SELECT role FROM users WHERE username='admin'"), "inventory_worker")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE role='admin'"), 0)

    def test_simultaneous_startups_create_only_one_admin(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(self.db.initialize) for _ in range(2)]
            for job in jobs:
                job.result(timeout=20)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE role='admin'"), 1)
        self.assertEqual(InventoryService(self.db).authenticate("admin", "Admin1234!").role, "admin")

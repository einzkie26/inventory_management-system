from decimal import Decimal
from pathlib import Path

from inventory.errors import DatabaseError
from inventory.services import InventoryService
from inventory.security import hash_password

from .mysql_support import MySQLTestCase


class MigrationTests(MySQLTestCase):
    def seed_users(self, *, balances=False):
        with self.db.transaction() as cursor:
            extra = ",balance DECIMAL(10,2) NOT NULL DEFAULT 0" if balances else ""
            cursor.execute(f"CREATE TABLE users (user_id INT AUTO_INCREMENT PRIMARY KEY,username VARCHAR(255) NOT NULL,email VARCHAR(100) NOT NULL,password VARCHAR(40) NOT NULL,role VARCHAR(8) NOT NULL{extra}) ENGINE=MyISAM")
            cursor.execute("INSERT INTO users (user_id,username,email,password,role) VALUES (11,'legacyadmin','legacyadmin@example.com','oldadmin','admin'),(12,'legacycustomer','legacy@example.org','oldcustomer','customer')")

    def test_original_users_only_database_gains_complete_schema_and_hashes(self):
        self.seed_users()
        self.db.initialize()
        service = InventoryService(self.db)
        self.assertEqual(service.authenticate("legacycustomer", "oldcustomer").user_id, 12)
        self.assertEqual(service.get_user(12).role, "inventory_worker")
        self.assertEqual(service.get_user(12).balance, Decimal("0.00"))
        self.assertEqual(service.list_products(11), [])
        self.assertTrue(self.scalar("SELECT password FROM users WHERE user_id=12").startswith("pbkdf2_sha256$"))
        self.assertEqual(self.scalar("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users'", (self.schema,)), "InnoDB")
        backups = list(self.db.settings.backup_dir.glob("*.sql"))
        self.assertEqual(len(backups), 1)
        self.db.initialize()
        self.assertEqual(len(list(self.db.settings.backup_dir.glob("*.sql"))), 1)

    def test_legacy_balances_orders_and_line_totals_survive_upgrade(self):
        self.seed_users(balances=True)
        with self.db.transaction() as cursor:
            cursor.execute("UPDATE users SET balance=123.45 WHERE user_id=12")
            cursor.execute("CREATE TABLE products (product_id INT AUTO_INCREMENT PRIMARY KEY,name VARCHAR(200),description VARCHAR(200),quantity INT,price DECIMAL(10,2),category VARCHAR(20))")
            cursor.execute("INSERT INTO products VALUES (21,'Legacy item','Description',4,20.00,'Groceries')")
            cursor.execute("CREATE TABLE orders (order_id INT AUTO_INCREMENT PRIMARY KEY,user_id INT,total_price DECIMAL(10,2),order_date DATETIME)")
            cursor.execute("INSERT INTO orders VALUES (31,12,100.00,'2024-12-19 14:48:22')")
            cursor.execute("CREATE TABLE order_details (detail_id INT AUTO_INCREMENT PRIMARY KEY,order_id INT,product_id INT,quantity INT,price DECIMAL(10,2))")
            cursor.execute("INSERT INTO order_details VALUES (41,31,21,5,100.00)")
        self.db.initialize()
        service = InventoryService(self.db)
        self.assertEqual(service.get_user(12).balance, Decimal("123.45"))
        self.assertEqual(service.list_products(11)[0].quantity, 4)
        order = service.sales.order_detail(11, 31)
        self.assertEqual(order["items"][0]["price"], Decimal("100.00"))
        self.assertEqual(order["items"][0]["unit_price"], Decimal("20.00"))
        self.assertEqual(order["username"], "legacycustomer")
        self.assertEqual(self.scalar("SELECT amount FROM balance_transactions WHERE user_id=12"), Decimal("123.45"))
        self.db.initialize()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM balance_transactions WHERE user_id=12"), 1)

    def test_duplicate_legacy_accounts_are_reported_without_deleting_records(self):
        self.seed_users()
        with self.db.transaction() as cursor:
            cursor.execute("INSERT INTO users (username,email,password,role) VALUES ('legacycustomer','duplicate@example.org','password','customer')")
        with self.assertRaisesRegex(DatabaseError, "duplicate"):
            self.db.initialize()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users"), 3)
        self.assertEqual(len(list(self.db.settings.backup_dir.glob("*.sql"))), 1)

    def test_legacy_cascading_deletes_become_restrictive(self):
        with self.db.transaction() as cursor:
            cursor.execute("CREATE TABLE users (user_id INT AUTO_INCREMENT PRIMARY KEY,username VARCHAR(255),email VARCHAR(100),password VARCHAR(40),role VARCHAR(8)) ENGINE=InnoDB")
            cursor.execute("CREATE TABLE orders (order_id INT AUTO_INCREMENT PRIMARY KEY,user_id INT NOT NULL,total_price DECIMAL(10,2),order_date DATETIME,CONSTRAINT old_orders_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE) ENGINE=InnoDB")
        self.db.initialize()
        self.assertEqual(self.scalar("SELECT DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=%s AND TABLE_NAME='orders'", (self.schema,)), "RESTRICT")

    def test_version_one_upgrade_preserves_admin_and_introduces_four_roles(self):
        schema_file = Path(__file__).resolve().parent.parent / "inventory" / "schema.sql"
        admin_hash = hash_password("Existing123!")
        with self.db.transaction() as cursor:
            for statement in schema_file.read_text(encoding="utf-8").split(";"):
                if statement.strip():
                    cursor.execute(statement)
            cursor.execute("INSERT INTO app_state VALUES (1,'Setup lock')")
            cursor.execute("INSERT INTO schema_migrations (version) VALUES (1)")
            cursor.execute("INSERT INTO users (user_id,username,email,password,role,balance) VALUES (11,'existingadmin','admin@example.com',%s,'admin',0),(12,'employee','employee@example.org',%s,'customer',123.45)", (admin_hash, admin_hash))
        self.db.initialize()
        self.assertEqual(self.scalar("SELECT password FROM users WHERE user_id=11"), admin_hash)
        self.assertEqual(InventoryService(self.db).authenticate("existingadmin", "Existing123!").user_id, 11)
        self.assertEqual(self.scalar("SELECT role FROM users WHERE user_id=11"), "admin")
        self.assertEqual(self.scalar("SELECT role FROM users WHERE user_id=12"), "inventory_worker")
        self.assertEqual(self.scalar("SELECT balance FROM users WHERE user_id=12"), Decimal("123.45"))
        self.assertEqual(self.scalar("SELECT MAX(version) FROM schema_migrations"), 2)
        self.assertEqual(len(list(self.db.settings.backup_dir.glob("*.sql"))), 1)
        self.db.initialize()
        self.assertEqual(len(list(self.db.settings.backup_dir.glob("*.sql"))), 1)

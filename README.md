# Inventory Management System

A Windows desktop app for employee inventory work, stock checks, deliveries, and sales, backed by live MySQL/XAMPP. The project began in 2024 and was later left unfinished; the current application uses the employee workflow described below.

## Run

1. Start **MySQL** in the XAMPP Control Panel.
2. Double-click **run.bat**, or run this command from the project folder:

   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```

The virtual environment is already prepared in this workspace. For a new checkout:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On startup, the system automatically creates the first admin account when no admin exists:

- **Username:** `admin`
- **Password:** `Admin1234!`

The password is stored as a salted hash. Restarting the app preserves existing admin credentials and does not create duplicates or reset changed passwords. After signing in, open **Employees → Add employee** and choose a role. Employee accounts are created by admins; there is no public customer registration or customer balance panel.

The original entry points, `loginandreg_menu.py` and `menu.py`, also launch the application. `python -m inventory` is supported. Python 3.10+ with Tkinter is required. This workspace was checked with Python 3.15, Tk 9, and XAMPP MariaDB 10.4.

## Employee roles

| Role | Panel and permissions |
| --- | --- |
| **Admin** | Employee roster and role management, product management, stock count review and correction, delivery assignment, and orders and sales. |
| **Inventory worker** | Add products, edit product details, add stock, assign deliveries, and view orders and sales. Stock reductions require an admin. |
| **Stock checker** | View physical, reserved, and available stock; record counts and flag differences; view count history and delivery manifests. Stock corrections require an admin. |
| **Truck delivery assistant** | See deliveries assigned to their account, inspect product names and quantities, recipient and destination, export manifests, and mark pickup and delivery completion. |

Admins can filter the employee roster by role, change roles, and deactivate accounts. The app keeps an active admin account. Pending deliveries must be reassigned or cancelled, and deliveries in transit completed, before a delivery assistant can be deactivated or moved to another role. Permissions are checked in the database-backed services as well as in navigation.

## Stock counts

1. The stock checker selects a product in **Check stock** and chooses **Record count**.
2. A difference appears in **Stock count flags**. Recording a count leaves stock unchanged.
3. An admin opens the flag and chooses **Apply correction**. The correction is recorded in the stock movement history.

If stock changes after a count, record a new count before applying a correction. A correction cannot remove units already reserved for assigned deliveries. New counts supersede older unresolved counts for the same product.

## Deliveries and sales

1. An admin or inventory worker opens **Deliveries → Assign delivery**.
2. Choose the recipient, destination, active delivery assistant, products, and quantities. Delivery notes are optional.
3. The assistant signs in and opens **My deliveries → Open manifest** to see the complete product list, quantities, destination, notes, and history.
4. **Mark picked up** records the products leaving the warehouse.
5. **Mark delivered** completes the delivery and the related order.

Stock on hand is the physical warehouse quantity. Assigned deliveries reserve units, so **available stock = stock on hand − reserved stock**. Pickup deducts the physical stock once and releases that delivery's reservation. Cancelling a delivery before pickup releases its reservations. Pending deliveries can be reassigned.

Each delivery creates an order with the selected product names, categories, unit prices, and quantities. Product edits preserve those snapshots. **Orders & sales** shows pending, in-transit, completed, and cancelled orders. Completed sales totals include completed deliveries and historical completed orders; assigning a pending delivery does not increase completed sales. No payment collection workflow is implemented.

Product and delivery rows are locked in a consistent order. Assignment, pickup, cancellation, stock changes, and audit records commit together. Exporting a receipt or manifest is a separate operation, so a file-write failure cannot undo a saved delivery. Archived products retain their order and delivery history.

## Verification

Unit tests run without a database; integration tests are opt-in:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -v

$env:INVENTORY_TEST_MYSQL = '1'
$env:INVENTORY_TEST_GUI = '1'
.\.venv\Scripts\python.exe -m unittest discover -v
```

Integration tests create and drop only randomly named `inventory_test_*` databases. They check all four roles, disabled accounts, stock flags, reservations, competing assignments and pickups, rollback after partial writes, legacy upgrades, backup restoration, and manifest export. The desktop test covers the full admin → inventory worker → stock checker → admin correction → delivery assistant → completed sale workflow and smaller window sizes.

Current desktop previews are in `artifacts/previews/`.

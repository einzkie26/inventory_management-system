"""Create the requested default admin once, without resetting existing accounts."""

from .errors import DatabaseError
from .security import hash_password

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "Admin1234!"
DEFAULT_ADMIN_EMAIL = "admin@inventory.local"


def ensure_default_admin(cursor) -> bool:
    """Seed an empty admin roster; disabled or customized admins remain unchanged."""
    cursor.execute("SELECT state_id FROM app_state WHERE state_id=1 FOR UPDATE")
    cursor.fetchone()
    cursor.execute("SELECT user_id FROM users WHERE role='admin' LIMIT 1 FOR UPDATE")
    if cursor.fetchone():
        return False
    cursor.execute(
        "SELECT user_id FROM users WHERE username=%s OR email=%s LIMIT 1 FOR UPDATE",
        (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL),
    )
    if cursor.fetchone():
        raise DatabaseError(
            "Cannot create the default admin because the username 'admin' or "
            "email 'admin@inventory.local' belongs to another employee. "
            "Rename that employee account in MySQL and restart."
        )
    cursor.execute(
        "INSERT INTO users (username,email,password,role,active) VALUES (%s,%s,%s,'admin',1)",
        (DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_EMAIL, hash_password(DEFAULT_ADMIN_PASSWORD)),
    )
    return True

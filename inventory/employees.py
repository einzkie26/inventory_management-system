"""Admin-only employee creation and role management."""

from .access import USER_FIELDS, require_user
from .errors import ValidationError
from .models import User
from .roles import ADMIN, ALL_ROLES, DELIVERY_ASSISTANT, INVENTORY_ROLES
from .validation import account_credentials


class EmployeeService:
    def __init__(self, database):
        self.database = database

    def list_employees(self, actor_id: int, search="", role=None) -> list[User]:
        if role is not None and role not in ALL_ROLES:
            raise ValidationError("Select a valid employee role.")
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, {ADMIN})
            term = "%" + search.strip() + "%"
            where = " WHERE (username LIKE %s OR email LIKE %s)"
            params = [term, term]
            if role:
                where += " AND role=%s"
                params.append(role)
            cursor.execute(f"SELECT {USER_FIELDS} FROM users{where} ORDER BY active DESC,username", tuple(params))
            return [User.from_row(row) for row in cursor.fetchall()]

    def create_employee(self, actor_id: int, username: str, email: str, password: str, role: str) -> User:
        if role not in ALL_ROLES:
            raise ValidationError("Select one of the four employee roles.")
        values = account_credentials(username, email, password)
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, {ADMIN})
            cursor.execute("INSERT INTO users (username,email,password,role) VALUES (%s,%s,%s,%s)", values + (role,))
            return require_user(cursor, cursor.lastrowid)

    def update_employee(self, actor_id: int, employee_id: int, *, role: str, active: bool) -> User:
        if role not in ALL_ROLES or not isinstance(active, bool):
            raise ValidationError("Select a valid employee role and account status.")
        with self.database.transaction() as cursor:
            # Serialize administrator changes so the final active admin cannot be removed.
            cursor.execute("SELECT state_id FROM app_state WHERE state_id=1 FOR UPDATE")
            cursor.fetchone()
            require_user(cursor, actor_id, {ADMIN}, lock=True)
            cursor.execute(f"SELECT {USER_FIELDS} FROM users WHERE user_id=%s FOR UPDATE", (employee_id,))
            target = cursor.fetchone()
            if target is None:
                raise ValidationError("This employee no longer exists.")
            if employee_id == actor_id and not active:
                raise ValidationError("Another admin must deactivate your account.")
            if target["role"] == ADMIN and target["active"] and (role != ADMIN or not active):
                cursor.execute("SELECT user_id FROM users WHERE role='admin' AND active=1 FOR UPDATE")
                if len(cursor.fetchall()) <= 1:
                    raise ValidationError("Keep at least one active admin account.")
            if target["role"] == DELIVERY_ASSISTANT and (role != DELIVERY_ASSISTANT or not active):
                cursor.execute(
                    "SELECT delivery_id FROM deliveries WHERE assigned_to=%s "
                    "AND status IN ('assigned','in_transit') FOR UPDATE", (employee_id,),
                )
                if cursor.fetchone():
                    raise ValidationError("Reassign pending deliveries and finish deliveries in transit before changing this employee.")
            cursor.execute("UPDATE users SET role=%s,active=%s WHERE user_id=%s", (role, active, employee_id))
            cursor.execute(f"SELECT {USER_FIELDS} FROM users WHERE user_id=%s", (employee_id,))
            return User.from_row(cursor.fetchone())

    def delivery_assistants(self, actor_id: int) -> list[dict]:
        with self.database.transaction() as cursor:
            require_user(cursor, actor_id, INVENTORY_ROLES)
            cursor.execute("SELECT user_id,username FROM users WHERE role='delivery_assistant' AND active=1 ORDER BY username")
            return cursor.fetchall()

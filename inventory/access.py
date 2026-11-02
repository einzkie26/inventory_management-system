"""Database-backed permission checks used for every employee operation."""

from .errors import AuthenticationError, PermissionDenied
from .models import User
from .roles import ALL_ROLES

USER_FIELDS = "user_id,username,email,role,balance,active"


def require_user(cursor, actor_id: int, roles=ALL_ROLES, *, lock=False) -> User:
    cursor.execute(
        f"SELECT {USER_FIELDS} FROM users WHERE user_id=%s" + (" FOR UPDATE" if lock else ""),
        (actor_id,),
    )
    row = cursor.fetchone()
    if row is None or not row["active"]:
        raise AuthenticationError("Your employee account is unavailable. Contact an admin.")
    if row["role"] not in roles:
        raise PermissionDenied("Your employee role does not allow this action.")
    return User.from_row(row)

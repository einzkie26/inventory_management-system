"""Validation shared by account setup and employee administration."""

import re

from .errors import ValidationError
from .security import hash_password


def account_credentials(username: str, email: str, password: str) -> tuple[str, str, str]:
    username, email = username.strip(), email.strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", username):
        raise ValidationError("Use 3–50 letters, numbers, dots, underscores, or hyphens for the username.")
    if len(email) > 254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise ValidationError("Enter a valid email address.")
    if not 8 <= len(password) <= 128 or not all((
        re.search(r"[a-z]", password), re.search(r"[A-Z]", password),
        re.search(r"[0-9]", password), re.search(r"[^A-Za-z0-9\s]", password),
    )):
        raise ValidationError("Use 8–128 characters, with uppercase and lowercase letters, a number, and a symbol.")
    return username, email, hash_password(password)


def required_text(value: str, label: str, maximum: int) -> str:
    value = value.strip()
    if not value or len(value) > maximum:
        raise ValidationError(f"{label} is required and must be at most {maximum:,} characters.")
    return value

"""Salted password hashes and transparent upgrades for the original accounts."""

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS)
    return f"{ALGORITHM}${ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> tuple[bool, bool]:
    """Return (matches, needs_upgrade); legacy plaintext is replaced on sign in."""
    if not isinstance(stored, str) or not stored:
        return False, False
    if not stored.startswith(ALGORITHM + "$"):
        return hmac.compare_digest(password.encode("utf-8"), stored.encode("utf-8")), True
    try:
        _, rounds, salt, expected = stored.split("$")
        iterations = int(rounds)
        if not 100_000 <= iterations <= 2_000_000:
            return False, False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
        return hmac.compare_digest(actual, bytes.fromhex(expected)), iterations < ITERATIONS
    except (TypeError, ValueError):
        return False, False

"""Password hashing with stdlib PBKDF2-HMAC-SHA256.

Format: ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.
"""

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 200_000


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = ITERATIONS) -> str:
    """Hash `password`. A random 16-byte salt is used unless one is given (the generator
    passes a seed-derived salt so that the same seed reproduces identical DB content)."""
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_s, salt_hex, digest_hex = encoded.split("$")
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    if algorithm != ALGORITHM or iterations < 1:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)

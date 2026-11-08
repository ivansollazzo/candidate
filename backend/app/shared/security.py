"""Cryptographic primitives without models: secret hashes, recovery keys, signed tokens.

Passwords and recovery keys are stored as Argon2 hashes (pwdlib); tokens are HS256 JWTs (PyJWT).
"""

import re
import secrets

import jwt
from pwdlib import PasswordHash

ALGORITHM = "HS256"
# Alphabet without ambiguous characters (0/O, 1/I/L)
KEY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
KEY_GROUPS, KEY_GROUP_SIZE = 6, 4

password_hash = PasswordHash.recommended()
# Used when the username doesn't exist, so response time stays the same
_DUMMY_HASH = password_hash.hash(secrets.token_hex(16))


def hash_secret(value: str) -> str:
    return password_hash.hash(value)


def verify_secret(value: str, hashed: str | None) -> bool:
    return password_hash.verify(value, hashed or _DUMMY_HASH) and hashed is not None


def new_recovery_key() -> str:
    """Key like "ABCD-EFGH-…": 24 random characters, about 119 bits."""
    chars = "".join(secrets.choice(KEY_ALPHABET) for _ in range(KEY_GROUPS * KEY_GROUP_SIZE))
    return "-".join(chars[i:i + KEY_GROUP_SIZE] for i in range(0, len(chars), KEY_GROUP_SIZE))


def normalize_recovery_key(value: str) -> str:
    chars = re.sub(r"[^A-Z0-9]", "", value.upper())
    return "-".join(chars[i:i + KEY_GROUP_SIZE] for i in range(0, len(chars), KEY_GROUP_SIZE))


def sign_token(claims: dict, secret: str) -> str:
    return jwt.encode(claims, secret, algorithm=ALGORITHM)


def read_token(token: str, secret: str) -> dict | None:
    """Claims of a valid, unexpired token; None otherwise."""
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None

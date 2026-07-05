"""Auth + secret encryption. Passwords: argon2. Sessions: JWT. Integration
secrets: Fernet (symmetric, key from env / KMS). Secrets are NEVER returned
to the client in plaintext — only masked."""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from .config import get_settings

_ph = PasswordHasher()
ALGO = "HS256"


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except VerifyMismatchError:
        return False


def create_token(sub: str, role: str, kind: str = "access") -> str:
    s = get_settings()
    ttl = (timedelta(minutes=s.jwt_access_ttl_min) if kind == "access"
           else timedelta(days=s.jwt_refresh_ttl_days))
    payload = {"sub": sub, "role": role, "kind": kind,
               "exp": datetime.now(timezone.utc) + ttl}
    return jwt.encode(payload, s.jwt_secret, algorithm=ALGO)


def decode_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGO])
    except JWTError:
        return None


def _fernet() -> Fernet:
    key = get_settings().secret_encryption_key
    if not key:
        # Dev fallback derived from JWT secret; production MUST set a real key.
        raw = get_settings().jwt_secret.encode()[:32].ljust(32, b"0")
        key = base64.urlsafe_b64encode(raw).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt_secret(ciphertext: bytes) -> str:
    return _fernet().decrypt(ciphertext).decode()

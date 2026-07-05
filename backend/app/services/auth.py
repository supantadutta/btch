"""Authentication: user store + register/authenticate on top of argon2 hashing
and JWT (core/security). The first user registered becomes admin; subsequent
users default to 'trader'. In-memory store for V1 dev; a DB-backed store is the
persistence follow-up (the interface is identical).

Passwords are never stored or returned in plaintext; only argon2 hashes are held.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from ..core.security import create_token, hash_password, verify_password

ROLES = ("admin", "trader", "viewer")


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    role: str
    created_at: float
    disabled: bool = False

    def public(self) -> dict:
        return {"id": self.id, "email": self.email, "role": self.role,
                "disabled": self.disabled}


class AuthError(Exception):
    pass


class UserStore:
    def __init__(self) -> None:
        self._by_email: Dict[str, User] = {}

    def register(self, email: str, password: str, role: Optional[str] = None) -> User:
        email = email.strip().lower()
        if not email or "@" not in email:
            raise AuthError("valid email required")
        if len(password) < 8:
            raise AuthError("password must be at least 8 characters")
        if email in self._by_email:
            raise AuthError("email already registered")
        # First user is admin; everyone else defaults to trader.
        assigned = role or ("admin" if not self._by_email else "trader")
        if assigned not in ROLES:
            raise AuthError(f"invalid role '{assigned}'")
        user = User(id=str(uuid.uuid4()), email=email, password_hash=hash_password(password),
                    role=assigned, created_at=time.time())
        self._by_email[email] = user
        return user

    def authenticate(self, email: str, password: str) -> User:
        user = self._by_email.get(email.strip().lower())
        if user is None or user.disabled or not verify_password(password, user.password_hash):
            raise AuthError("invalid credentials")
        return user

    def get(self, email: str) -> Optional[User]:
        return self._by_email.get(email.strip().lower())

    def count(self) -> int:
        return len(self._by_email)


def issue_tokens(user: User) -> dict:
    return {
        "access": create_token(user.email, user.role, "access"),
        "refresh": create_token(user.email, user.role, "refresh"),
        "user": user.public(),
    }

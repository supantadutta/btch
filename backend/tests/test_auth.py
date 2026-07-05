"""Auth: user store, password hashing, roles, and JWT round-trip."""
import pytest

from app.core.security import decode_token
from app.services.auth import AuthError, UserStore, issue_tokens


def test_first_user_is_admin():
    s = UserStore()
    u = s.register("a@x.com", "password1")
    assert u.role == "admin"


def test_second_user_is_trader():
    s = UserStore()
    s.register("a@x.com", "password1")
    u2 = s.register("b@x.com", "password2")
    assert u2.role == "trader"


def test_password_is_hashed_not_stored_plaintext():
    s = UserStore()
    u = s.register("a@x.com", "password1")
    assert u.password_hash != "password1"
    assert "password1" not in u.password_hash
    assert u.public().get("password_hash") is None  # never serialized


def test_authenticate_success_and_failure():
    s = UserStore()
    s.register("a@x.com", "password1")
    assert s.authenticate("a@x.com", "password1").email == "a@x.com"
    with pytest.raises(AuthError):
        s.authenticate("a@x.com", "wrong")
    with pytest.raises(AuthError):
        s.authenticate("nobody@x.com", "password1")


def test_duplicate_email_rejected():
    s = UserStore()
    s.register("a@x.com", "password1")
    with pytest.raises(AuthError):
        s.register("A@X.com", "password2")   # case-insensitive


def test_short_password_and_bad_email_rejected():
    s = UserStore()
    with pytest.raises(AuthError):
        s.register("a@x.com", "short")
    with pytest.raises(AuthError):
        s.register("notanemail", "password1")


def test_issue_tokens_roundtrip_encodes_role():
    s = UserStore()
    u = s.register("a@x.com", "password1")
    toks = issue_tokens(u)
    claims = decode_token(toks["access"])
    assert claims["sub"] == "a@x.com" and claims["role"] == "admin"
    assert claims["kind"] == "access"
    refresh = decode_token(toks["refresh"])
    assert refresh["kind"] == "refresh"
    assert toks["user"]["role"] == "admin"

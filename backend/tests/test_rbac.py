"""Role-based access control on the require_role dependency.

Verifies the gate is a no-op when auth is disabled (dev/paper default) and
enforces token + role when enabled — without needing the full app running."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.auth_routes import require_role
from app.core.security import create_token


def _request(auth_required: bool):
    settings = SimpleNamespace(auth_required=auth_required)
    runtime = SimpleNamespace(settings=settings)
    app = SimpleNamespace(state=SimpleNamespace(runtime=runtime))
    return SimpleNamespace(app=app)


async def _call(dep_obj, auth_required, authorization=None):
    dep = dep_obj.dependency          # unwrap Depends(...)
    return await dep(_request(auth_required), authorization=authorization)


async def test_noop_when_auth_disabled():
    # No token, but auth disabled → allowed (returns None).
    assert await _call(require_role("admin"), auth_required=False) is None


async def test_requires_token_when_enabled():
    with pytest.raises(HTTPException) as e:
        await _call(require_role("admin"), auth_required=True, authorization=None)
    assert e.value.status_code == 401


async def test_rejects_wrong_role():
    token = create_token("u@x.com", "viewer", "access")
    with pytest.raises(HTTPException) as e:
        await _call(require_role("admin"), auth_required=True,
                    authorization=f"Bearer {token}")
    assert e.value.status_code == 403


async def test_allows_matching_role():
    token = create_token("a@x.com", "admin", "access")
    claims = await _call(require_role("admin", "trader"), auth_required=True,
                         authorization=f"Bearer {token}")
    assert claims["role"] == "admin"


async def test_bad_token_rejected():
    with pytest.raises(HTTPException) as e:
        await _call(require_role("admin"), auth_required=True,
                    authorization="Bearer not.a.jwt")
    assert e.value.status_code == 401

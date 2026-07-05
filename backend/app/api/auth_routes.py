"""Auth endpoints + current-user dependency.

RBAC is opt-in in V1 via AUTH_REQUIRED (config). When off, the dev/paper demo
runs without tokens; when on, mutating routes can require a role. The auth
system itself is always available so it can be exercised and tested.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..core.security import decode_token
from ..schemas.api import LoginRequest
from ..services.auth import AuthError, UserStore, issue_tokens

auth_router = APIRouter(prefix="/api/v1/auth")


def _store(request: Request) -> UserStore:
    return request.app.state.runtime.users


@auth_router.post("/register")
async def register(request: Request, body: LoginRequest):
    try:
        user = _store(request).register(body.email, body.password)
    except AuthError as e:
        raise HTTPException(400, str(e))
    request.app.state.runtime.audit.record(user.email, "auth.register", "user", user.id,
                                            after={"role": user.role})
    return {"data": issue_tokens(user)}


@auth_router.post("/login")
async def login(request: Request, body: LoginRequest):
    try:
        user = _store(request).authenticate(body.email, body.password)
    except AuthError as e:
        raise HTTPException(401, str(e))
    return {"data": issue_tokens(user)}


@auth_router.post("/refresh")
async def refresh(request: Request, authorization: Optional[str] = Header(None)):
    claims = _bearer_claims(authorization)
    if not claims or claims.get("kind") != "refresh":
        raise HTTPException(401, "valid refresh token required")
    user = _store(request).get(claims["sub"])
    if user is None:
        raise HTTPException(401, "unknown user")
    return {"data": issue_tokens(user)}


@auth_router.get("/me")
async def me(request: Request, authorization: Optional[str] = Header(None)):
    claims = _bearer_claims(authorization)
    if not claims:
        raise HTTPException(401, "authentication required")
    user = _store(request).get(claims["sub"])
    if user is None:
        raise HTTPException(401, "unknown user")
    return {"data": user.public()}


# ── helpers / dependency ────────────────────────────────────────────

def _bearer_claims(authorization: Optional[str]) -> Optional[dict]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return decode_token(authorization.split(" ", 1)[1])


def require_role(*roles: str):
    """Dependency factory. No-op when AUTH_REQUIRED is off (dev/paper); enforces
    a bearer token with an allowed role when on."""
    async def dep(request: Request, authorization: Optional[str] = Header(None)):
        if not getattr(request.app.state.runtime.settings, "auth_required", False):
            return None
        claims = _bearer_claims(authorization)
        if not claims:
            raise HTTPException(401, "authentication required")
        if roles and claims.get("role") not in roles:
            raise HTTPException(403, f"requires role in {roles}")
        return claims
    return Depends(dep)

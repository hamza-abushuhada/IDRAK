from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, Request

from . import db
from .config import settings

ROLE_RANK = {"cashier": 1, "accountant": 2, "manager": 3, "owner": 4}

PERMISSIONS = {
    "view_dashboard": "cashier",
    "view_sales": "cashier",
    "view_finance": "accountant",
    "upload_data": "manager",
    "clean_data": "manager",
    "manage_inventory": "manager",
    "send_supplier_email": "manager",
    "manage_alerts": "manager",
    "manage_team": "owner",
    "manage_billing": "owner",
    "manage_org": "owner",
    "view_audit": "manager",
}


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json")


def decode_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") == "HS256":
            return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        key = _jwks_client().get_signing_key_from_jwt(token).key
        return jwt.decode(token, key, algorithms=[header.get("alg", "ES256")], audience="authenticated")
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Invalid session: {e}") from e


@dataclass
class User:
    id: str
    email: str
    full_name: str | None
    is_super_admin: bool


@dataclass
class Ctx:
    user: User
    org_id: str
    role: str

    def can(self, perm: str) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK[PERMISSIONS[perm]]


async def current_user(request: Request, authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    claims = decode_token(authorization.split(" ", 1)[1])
    uid = claims["sub"]
    email = claims.get("email", "")
    meta = claims.get("user_metadata") or {}
    prof = db.cache_get(("profile", uid), 60) or await db.fetchrow("select full_name, is_super_admin from profiles where id=$1", uid)
    if prof is not None:
        db.cache_set(("profile", uid), prof)
    if prof is None:
        await db.execute(
            "insert into profiles(id, full_name, locale) values($1,$2,$3) on conflict (id) do nothing",
            uid, meta.get("full_name") or email.split("@")[0], meta.get("locale") or "ar",
        )
        prof = {"full_name": meta.get("full_name"), "is_super_admin": False}
    user = User(uid, email, prof["full_name"], prof["is_super_admin"])
    request.state.user = user
    return user


async def org_ctx(user: User = Depends(current_user), x_org_id: str | None = Header(default=None)) -> Ctx:
    if not x_org_id:
        raise HTTPException(400, "Missing X-Org-Id header")
    import re as _re
    if not _re.fullmatch(r"[0-9a-fA-F-]{36}", x_org_id):
        raise HTTPException(400, "Bad X-Org-Id")
    m = db.cache_get(("member", user.id, x_org_id), 30) or await db.fetchrow("select role from memberships where org_id=$1 and user_id=$2", x_org_id, user.id)
    if m is not None:
        db.cache_set(("member", user.id, x_org_id), m)
    if m is None:
        raise HTTPException(403, "You are not a member of this business")
    return Ctx(user, x_org_id, m["role"])


def require(perm: str):
    async def dep(ctx: Ctx = Depends(org_ctx)) -> Ctx:
        if not ctx.can(perm):
            raise HTTPException(403, f"Your role ({ctx.role}) cannot do this")
        return ctx
    return dep


async def super_admin(user: User = Depends(current_user)) -> User:
    if not user.is_super_admin:
        raise HTTPException(403, "Founder console only")
    return user

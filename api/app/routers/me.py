import html
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import db
from ..auth import Ctx, User, current_user, org_ctx, require
from ..config import settings
from ..services import email

router = APIRouter(tags=["account"])


@router.get("/me")
async def me(user: User = Depends(current_user)):
    orgs = await db.fetch("""select o.id, o.name, o.name_ar, o.industry, o.city, o.plan, o.onboarding_completed, o.is_demo, m.role,
                                    (select count(*) from branches b where b.org_id=o.id) branches
                             from memberships m join organizations o on o.id=m.org_id where m.user_id=$1 order by o.created_at""", user.id)
    prof = await db.fetchrow("select full_name, locale, is_super_admin from profiles where id=$1", user.id)
    return {"id": user.id, "email": user.email, "full_name": prof["full_name"], "locale": prof["locale"], "is_super_admin": prof["is_super_admin"], "orgs": orgs}


class ProfilePatch(BaseModel):
    full_name: str | None = None
    locale: str | None = None


@router.patch("/me")
async def patch_me(p: ProfilePatch, user: User = Depends(current_user)):
    await db.execute("update profiles set full_name=coalesce($2, full_name), locale=coalesce($3, locale) where id=$1", user.id, p.full_name, p.locale)
    return {"ok": True}


class BranchIn(BaseModel):
    name: str
    name_ar: str | None = None
    city: str | None = None
    area: str | None = None


class OrgIn(BaseModel):
    name: str
    name_ar: str | None = None
    industry: str = "minimarket"
    city: str | None = "Amman"
    locale: str = "ar"
    tax_number: str | None = None
    branches: list[BranchIn] = []


@router.post("/orgs")
async def create_org(o: OrgIn, user: User = Depends(current_user)):
    slug = re.sub(r"[^a-z0-9]+", "-", o.name.lower()).strip("-")[:40] + "-" + secrets.token_hex(2)
    async with db.transaction() as c:
        org_id = await c.fetchval("""insert into organizations(name,name_ar,slug,industry,city,locale,tax_number,onboarding_completed,plan)
                                     values($1,$2,$3,$4,$5,$6,$7,true,'growth') returning id""", o.name, o.name_ar, slug, o.industry, o.city, o.locale, o.tax_number)
        await c.execute("insert into memberships(org_id,user_id,role) values($1,$2,'owner')", org_id, user.id)
        for b in o.branches or [BranchIn(name="Main branch", name_ar="الفرع الرئيسي", city=o.city)]:
            await c.execute("insert into branches(org_id,name,name_ar,city,area) values($1,$2,$3,$4,$5)", org_id, b.name, b.name_ar, b.city or o.city, b.area)
    await db.audit(str(org_id), user.id, "org.created", "organization", str(org_id), {"name": o.name})
    ar = o.locale == "ar"
    body = ("<p>" + ("أهلاً فيك بإدراك! حسابك جاهز. أول خطوة: ارفع ملف مبيعات أو مخزون وخلّي إدراك ينظّفه ويطلعلك وين عم تخسر." if ar else
                     "Welcome to Idrak! Your workspace is ready. First step: upload a sales or stock file and let Idrak clean it and show you where you're losing money.") + "</p>")
    await email.send(user.email, "أهلاً بك في إدراك" if ar else "Welcome to Idrak",
                     email.layout(f"{'أهلاً' if ar else 'Welcome'} {html.escape(user.full_name or '')}", body, o.locale, ("افتح إدراك" if ar else "Open Idrak", f"{settings.web_url}/{o.locale}/app")))
    return {"id": str(org_id)}


@router.post("/me/join-demo")
async def join_demo(user: User = Depends(current_user)):
    org = await db.fetchval("select id from organizations where slug='al-nashama'")
    if not org:
        raise HTTPException(404, "Demo data not seeded")
    await db.execute("insert into memberships(org_id,user_id,role) values($1,$2,'manager') on conflict do nothing", org, user.id)
    return {"id": org}


@router.get("/org")
async def get_org(ctx: Ctx = Depends(org_ctx)):
    o = await db.fetchrow("select * from organizations where id=$1", ctx.org_id)
    o["branches"] = await db.fetch("select id,name,name_ar,city,area,lat,lng,opened_at from branches where org_id=$1 order by name", ctx.org_id)
    o["role"] = ctx.role
    o["usage"] = await db.fetchrow("""select (select count(*) from uploads where org_id=$1 and created_at > now() - interval '30 days') uploads_30d,
        (select coalesce(sum(row_count),0) from uploads where org_id=$1 and created_at > now() - interval '30 days') rows_30d,
        (select count(*) from ai_usage where org_id=$1 and created_at > now() - interval '30 days') ai_calls_30d,
        (select count(*) from memberships where org_id=$1) members""", ctx.org_id)
    return o


class OrgPatch(BaseModel):
    name: str | None = None
    name_ar: str | None = None
    industry: str | None = None
    city: str | None = None
    tax_number: str | None = None
    locale: str | None = None
    monthly_rent: float | None = None
    opening_cash: float | None = None
    plan: str | None = None


@router.patch("/org")
async def patch_org(p: OrgPatch, ctx: Ctx = Depends(require("manage_org"))):
    data = {k: v for k, v in p.model_dump().items() if v is not None}
    if not data:
        return {"ok": True}
    sets = ", ".join(f"{k}=${i + 2}" for i, k in enumerate(data))
    await db.execute(f"update organizations set {sets} where id=$1", ctx.org_id, *data.values())
    await db.audit(ctx.org_id, ctx.user.id, "settings.updated", "organization", ctx.org_id, data)
    return {"ok": True}


@router.post("/org/branches")
async def add_branch(b: BranchIn, ctx: Ctx = Depends(require("manage_org"))):
    bid = await db.fetchval("insert into branches(org_id,name,name_ar,city,area) values($1,$2,$3,$4,$5) returning id", ctx.org_id, b.name, b.name_ar, b.city, b.area)
    await db.audit(ctx.org_id, ctx.user.id, "branch.created", "branch", str(bid), {"name": b.name})
    return {"id": str(bid)}


@router.get("/team")
async def team(ctx: Ctx = Depends(org_ctx)):
    members = await db.fetch("""select m.id, m.role, m.created_at, u.email, p.full_name from memberships m join auth.users u on u.id=m.user_id
                                left join profiles p on p.id=m.user_id where m.org_id=$1 order by m.created_at""", ctx.org_id)
    invites = await db.fetch("select id,email,role,status,created_at,expires_at from invitations where org_id=$1 and status='pending' order by created_at desc", ctx.org_id)
    return {"members": members, "invites": invites, "my_role": ctx.role}


class InviteIn(BaseModel):
    email: str
    role: str = "manager"


@router.post("/team/invite")
async def invite(i: InviteIn, ctx: Ctx = Depends(require("manage_team"))):
    if i.role not in ("owner", "manager", "accountant", "cashier"):
        raise HTTPException(422, "Bad role")
    token = secrets.token_urlsafe(24)
    await db.execute("insert into invitations(org_id,email,role,token,invited_by) values($1,$2,$3,$4,$5)", ctx.org_id, i.email.lower().strip(), i.role, token, ctx.user.id)
    org = await db.fetchrow("select name, name_ar, locale from organizations where id=$1", ctx.org_id)
    loc = org["locale"] or "ar"
    ar = loc == "ar"
    link = f"{settings.web_url}/{loc}/invite/{token}"
    roles_ar = {"owner": "مالك", "manager": "مدير", "accountant": "محاسب", "cashier": "كاشير"}
    body = (f"<p>{html.escape(ctx.user.full_name or ctx.user.email)} " + (f"دعاك تنضم لـ <b>{html.escape(org['name_ar'] or org['name'])}</b> على إدراك كـ {roles_ar[i.role]}." if ar else
            f"invited you to join <b>{html.escape(org['name'])}</b> on Idrak as {i.role}.") + "</p>")
    res = await email.send(i.email, "دعوة للانضمام إلى إدراك" if ar else "You're invited to Idrak", email.layout("دعوة فريق" if ar else "Team invitation", body, loc, ("قبول الدعوة" if ar else "Accept invitation", link)))
    await db.audit(ctx.org_id, ctx.user.id, "team.invited", "invitation", i.email, {"role": i.role, "email_ok": res.get("ok")})
    return {"ok": True, "link": link, "email": res}


@router.get("/invitations/{token}")
async def get_invite(token: str):
    inv = await db.fetchrow("""select i.email, i.role, i.status, i.expires_at, o.name, o.name_ar from invitations i join organizations o on o.id=i.org_id where token=$1""", token)
    if not inv:
        raise HTTPException(404, "Invitation not found")
    return inv


@router.post("/invitations/{token}/accept")
async def accept_invite(token: str, user: User = Depends(current_user)):
    inv = await db.fetchrow("select * from invitations where token=$1 and status='pending' and expires_at > now()", token)
    if not inv:
        raise HTTPException(404, "Invitation expired or already used")
    await db.execute("insert into memberships(org_id,user_id,role) values($1,$2,$3) on conflict (org_id,user_id) do update set role=excluded.role", inv["org_id"], user.id, inv["role"])
    await db.execute("update invitations set status='accepted' where id=$1", inv["id"])
    await db.audit(inv["org_id"], user.id, "team.joined", "membership", user.id, {"role": inv["role"]})
    return {"org_id": inv["org_id"]}


class RolePatch(BaseModel):
    role: str


@router.patch("/team/{membership_id}")
async def change_role(membership_id: str, p: RolePatch, ctx: Ctx = Depends(require("manage_team"))):
    await db.execute("update memberships set role=$3 where id=$1 and org_id=$2", membership_id, ctx.org_id, p.role)
    await db.audit(ctx.org_id, ctx.user.id, "team.role_changed", "membership", membership_id, {"role": p.role})
    return {"ok": True}


@router.delete("/team/{membership_id}")
async def remove_member(membership_id: str, ctx: Ctx = Depends(require("manage_team"))):
    owners = await db.fetchval("select count(*) from memberships where org_id=$1 and role='owner'", ctx.org_id)
    target = await db.fetchrow("select role, user_id from memberships where id=$1 and org_id=$2", membership_id, ctx.org_id)
    if target and target["role"] == "owner" and owners <= 1:
        raise HTTPException(400, "Can't remove the last owner")
    await db.execute("delete from memberships where id=$1 and org_id=$2", membership_id, ctx.org_id)
    await db.audit(ctx.org_id, ctx.user.id, "team.removed", "membership", membership_id)
    return {"ok": True}


@router.delete("/team/invites/{invite_id}")
async def revoke_invite(invite_id: str, ctx: Ctx = Depends(require("manage_team"))):
    await db.execute("update invitations set status='revoked' where id=$1 and org_id=$2", invite_id, ctx.org_id)
    return {"ok": True}


@router.get("/notifications")
async def notifications(ctx: Ctx = Depends(org_ctx)):
    rows = await db.fetch("select * from notifications where org_id=$1 and (user_id is null or user_id=$2) order by created_at desc limit 30", ctx.org_id, ctx.user.id)
    return {"items": rows, "unread": sum(1 for r in rows if not r["read_at"])}


@router.post("/notifications/read")
async def read_all(ctx: Ctx = Depends(org_ctx)):
    await db.execute("update notifications set read_at=now() where org_id=$1 and read_at is null", ctx.org_id)
    return {"ok": True}


@router.get("/audit")
async def audit_log(ctx: Ctx = Depends(require("view_audit"))):
    return await db.fetch("""select a.*, p.full_name from audit_log a left join profiles p on p.id=a.user_id
                             where a.org_id=$1 order by a.created_at desc limit 200""", ctx.org_id)

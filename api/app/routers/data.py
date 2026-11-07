import datetime as dt
import re
import uuid
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import db
from ..auth import Ctx, require
from ..cleaning import engine
from ..cleaning.arabic import match_key
from ..cleaning.context import load_context
from ..cleaning.fields import ENTITY_LABELS, FIELDS, LABELS, auto_map, detect_entity, kind_of
from ..cleaning.io import read_table
from ..services import ai

router = APIRouter(prefix="/data", tags=["data"])
MERGE_RULES = {"product_match", "person_match", "branch_map", "value_merge", "payment_map", "city_map"}


def _field_catalog():
    return [{"key": k, "kind": v[0], "en": LABELS[k][0], "ar": LABELS[k][1]} for k, v in FIELDS.items()]


async def _create_upload(ctx: Ctx, filename: str, data: bytes, source: str = "upload"):
    try:
        headers, rows, sheets = read_table(filename, data)
    except Exception as e:
        raise HTTPException(422, f"Could not read this file: {e}") from e
    if not headers:
        raise HTTPException(422, "No header row found")
    mapping = auto_map(headers)
    unmapped = [h for h, m in mapping.items() if not m["field"]]
    if unmapped:
        samples = {h: [r[i] for r in rows[:8] if r[i] not in (None, "")] for i, h in enumerate(headers)}
        ai_map = await ai.map_columns(headers, samples, ctx.org_id, ctx.user.id)
        if ai_map:
            used = {m["field"] for m in mapping.values() if m["field"]}
            for h in unmapped:
                f = (ai_map.get(h) or {}).get("field")
                if f in FIELDS and f not in used:
                    mapping[h] = {"field": f, "confidence": float((ai_map[h] or {}).get("confidence") or 0.7), "source": "ai", "reason": ai_map[h].get("reason")}
                    used.add(f)
    entity = detect_entity({m["field"] for m in mapping.values() if m["field"]})
    uid = await db.fetchval("""insert into uploads(org_id,uploaded_by,file_name,file_size,source,entity,sheet_name,row_count,column_count,columns,mapping,status)
                               values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'mapped') returning id""",
                            ctx.org_id, ctx.user.id, filename, len(data), source, entity, sheets[0] if sheets else None, len(rows), len(headers), headers, mapping)
    safe_rows = [[v if isinstance(v, (int, float, str)) or v is None else str(v) for v in r] for r in rows]
    await db.execute("insert into upload_data(upload_id, org_id, raw_rows) values($1,$2,$3)", uid, ctx.org_id, safe_rows)
    await db.audit(ctx.org_id, ctx.user.id, "upload.created", "upload", str(uid), {"file": filename, "rows": len(rows)})
    return await get_upload(str(uid), ctx)


@router.get("/fields")
async def fields():
    return {"fields": _field_catalog(), "entities": {k: {"en": v[0], "ar": v[1]} for k, v in ENTITY_LABELS.items()}}


@router.post("/uploads")
async def upload(file: UploadFile = File(...), ctx: Ctx = Depends(require("upload_data"))):
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 15MB)")
    return await _create_upload(ctx, file.filename or "upload.csv", data)


class UrlIn(BaseModel):
    url: str


@router.post("/import-url")
async def import_url(u: UrlIn, ctx: Ctx = Depends(require("upload_data"))):
    m = re.search(r"docs\.google\.com/spreadsheets/d/([\w-]+)", u.url)
    if not m:
        raise HTTPException(422, "Paste a Google Sheets share link (Anyone with the link can view)")
    gid = re.search(r"gid=(\d+)", u.url)
    url = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as cx:
        r = await cx.get(url)
    if r.status_code != 200 or "text/html" in r.headers.get("content-type", ""):
        raise HTTPException(422, "Couldn't open the sheet. Make sure sharing is set to 'Anyone with the link'.")
    return await _create_upload(ctx, "google-sheet.csv", r.content, source="google_sheet")


@router.get("/uploads")
async def list_uploads(ctx: Ctx = Depends(require("view_dashboard"))):
    return await db.fetch("""select u.id, u.file_name, u.file_size, u.source, u.entity, u.row_count, u.column_count, u.status, u.health_before, u.health_after,
                                    u.imported_rows, u.created_at, p.full_name uploaded_by_name,
                                    (select id from cleaning_runs r where r.upload_id=u.id order by started_at desc limit 1) last_run_id,
                                    exists(select 1 from upload_data d where d.upload_id=u.id) has_data
                             from uploads u left join profiles p on p.id=u.uploaded_by where u.org_id=$1 order by u.created_at desc""", ctx.org_id)


@router.get("/uploads/{upload_id}")
async def get_upload(upload_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    u = await db.fetchrow("select * from uploads where id=$1 and org_id=$2", upload_id, ctx.org_id)
    if not u:
        raise HTTPException(404, "Upload not found")
    d = await db.fetchrow("select raw_rows from upload_data where upload_id=$1", upload_id)
    u["preview"] = (d["raw_rows"][:25] if d else [])
    u["fields"] = _field_catalog()
    u["entity_label"] = ENTITY_LABELS.get(u["entity"], ENTITY_LABELS["unknown"])
    u["last_run_id"] = await db.fetchval("select id from cleaning_runs where upload_id=$1 order by started_at desc limit 1", upload_id)
    return u


class MappingIn(BaseModel):
    mapping: dict[str, str | None]


@router.put("/uploads/{upload_id}/mapping")
async def set_mapping(upload_id: str, m: MappingIn, ctx: Ctx = Depends(require("upload_data"))):
    u = await db.fetchrow("select mapping from uploads where id=$1 and org_id=$2", upload_id, ctx.org_id)
    if not u:
        raise HTTPException(404)
    cur = u["mapping"] or {}
    for h, f in m.mapping.items():
        cur[h] = {**(cur.get(h) or {}), "field": f if f in FIELDS else None, "source": "user", "confidence": 1.0}
    entity = detect_entity({v["field"] for v in cur.values() if v.get("field")})
    await db.execute("update uploads set mapping=$3, entity=$4 where id=$1 and org_id=$2", upload_id, ctx.org_id, cur, entity)
    return {"ok": True, "entity": entity}


@router.post("/uploads/{upload_id}/clean")
async def clean(upload_id: str, ctx: Ctx = Depends(require("clean_data"))):
    u = await db.fetchrow("select * from uploads where id=$1 and org_id=$2", upload_id, ctx.org_id)
    d = await db.fetchrow("select raw_rows from upload_data where upload_id=$1", upload_id)
    if not u or not d:
        raise HTTPException(404, "Upload data not found")
    headers = u["columns"]
    mapping = {h: (u["mapping"].get(h) or {}).get("field") for h in headers}
    ctxk = await load_context(ctx.org_id)
    res = engine.run(headers, d["raw_rows"], mapping, ctxk)
    memory_hits = sum(1 for c in res["changes"] if c["rule"] == "memory")
    stats = {"rows_before": res["rows_before"], "rows_after": res["rows_after"], "issues": res["issues"], "clusters": res["clusters"],
             "flags": res["flags"][:500], "flag_count": len(res["flags"]), "entity": res["entity"], "memory_hits": memory_hits,
             "removed_rows": res["removed_rows"]}
    async with db.transaction() as c:
        run_id = await c.fetchval("""insert into cleaning_runs(org_id,upload_id,status,score_before,score_after,stats,created_by,finished_at)
                                     values($1,$2,'review',$3,$4,$5,$6,now()) returning id""", ctx.org_id, upload_id, res["score_before"], res["score_after"], stats, ctx.user.id)
        recs = [(ctx.org_id, run_id, ch["row"], ch["column"], ch["old"][:500], (ch["new"] or "")[:500], ch["rule"], ch["category"], ch["confidence"], ch["group"], "proposed")
                for ch in res["changes"]]
        if recs:
            import uuid
            await c.copy_records_to_table("cleaning_changes", records=[(uuid.uuid4(), *r) for r in recs],
                                          columns=["id", "org_id", "run_id", "row_index", "column_name", "old_value", "new_value", "rule", "category", "confidence", "group_key", "status"])
        await c.execute("update uploads set status='cleaned', health_before=$2, health_after=$3, entity=$4 where id=$1",
                        upload_id, res["score_before"]["score"], res["score_after"]["score"], res["entity"])
    await db.audit(ctx.org_id, ctx.user.id, "cleaning.run", "upload", upload_id, {"before": res["score_before"]["score"], "after": res["score_after"]["score"]})
    return await get_run(str(run_id), ctx)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    r = await db.fetchrow("""select r.*, u.file_name, u.columns, u.mapping, u.row_count, u.entity from cleaning_runs r join uploads u on u.id=r.upload_id
                             where r.id=$1 and r.org_id=$2""", run_id, ctx.org_id)
    if not r:
        raise HTTPException(404, "Run not found")
    counts = await db.fetch("select rule, status, count(*) n from cleaning_changes where run_id=$1 group by 1,2", run_id)
    by_rule = defaultdict(lambda: {"proposed": 0, "approved": 0, "rejected": 0, "reverted": 0})
    for c in counts:
        by_rule[c["rule"]][c["status"]] += c["n"]
    r["rule_status"] = by_rule
    r["totals"] = {s: sum(v[s] for v in by_rule.values()) for s in ("proposed", "approved", "rejected", "reverted")}
    r["rules_meta"] = {k: {"en": v[0], "ar": v[1], "category": v[2]} for k, v in engine.RULES.items()}
    r["flags_meta"] = {k: {"en": v[0], "ar": v[1]} for k, v in engine.FLAGS.items()}
    r["labels"] = {k: {"en": v[0], "ar": v[1]} for k, v in LABELS.items()}
    return r


@router.get("/runs/{run_id}/changes")
async def run_changes(run_id: str, rule: str | None = None, status: str | None = None, offset: int = 0, limit: int = 200,
                      ctx: Ctx = Depends(require("view_dashboard"))):
    where, args = "run_id=$1 and org_id=$2", [run_id, ctx.org_id]
    if rule:
        args.append(rule)
        where += f" and rule=${len(args)}"
    if status:
        args.append(status)
        where += f" and status=${len(args)}"
    total = await db.fetchval(f"select count(*) from cleaning_changes where {where}", *args)
    items = await db.fetch(f"select * from cleaning_changes where {where} order by row_index, column_name offset {int(offset)} limit {min(int(limit), 1000)}", *args)
    return {"total": total, "items": items}


@router.get("/runs/{run_id}/grid")
async def run_grid(run_id: str, offset: int = 0, limit: int = 100, only_changed: bool = False, ctx: Ctx = Depends(require("view_dashboard"))):
    r = await db.fetchrow("select r.upload_id, r.stats, u.columns from cleaning_runs r join uploads u on u.id=r.upload_id where r.id=$1 and r.org_id=$2", run_id, ctx.org_id)
    if not r:
        raise HTTPException(404)
    d = await db.fetchrow("select raw_rows from upload_data where upload_id=$1", r["upload_id"])
    raw = d["raw_rows"]
    ch = await db.fetch("select id,row_index,column_name,old_value,new_value,rule,status,confidence from cleaning_changes where run_id=$1", run_id)
    by_row = defaultdict(dict)
    for c in ch:
        by_row[c["row_index"]][c["column_name"]] = c
    flags = defaultdict(dict)
    for f in (r["stats"] or {}).get("flags", []):
        flags[f["row"]][f["column"]] = f["reason"]
    idxs = sorted(by_row) if only_changed else list(range(len(raw)))
    total = len(idxs)
    out = []
    for i in idxs[offset: offset + limit]:
        row = raw[i]
        cells = []
        for ci, h in enumerate(r["columns"]):
            c = by_row[i].get(h)
            v = row[ci] if ci < len(row) else None
            cells.append({"v": "" if v is None else str(v), "change": c, "flag": flags[i].get(h)})
        out.append({"i": i, "cells": cells, "row_change": by_row[i].get("*")})
    return {"columns": r["columns"], "total": total, "rows": out}


class Decision(BaseModel):
    status: str
    ids: list[str] | None = None
    rule: str | None = None
    group: str | None = None
    all: bool = False


@router.post("/runs/{run_id}/decide")
async def decide(run_id: str, d: Decision, ctx: Ctx = Depends(require("clean_data"))):
    if d.status not in ("approved", "rejected", "proposed"):
        raise HTTPException(422)
    where, args = "run_id=$1 and org_id=$2", [run_id, ctx.org_id, d.status]
    if d.ids:
        args.append(d.ids)
        where += f" and id = any(${len(args)}::uuid[])"
    elif d.rule:
        args.append(d.rule)
        where += f" and rule=${len(args)}"
    elif d.group:
        args.append(d.group)
        where += f" and group_key=${len(args)}"
    elif not d.all:
        raise HTTPException(422, "Nothing selected")
    res = await db.execute(f"update cleaning_changes set status=$3 where {where}", *args)
    return {"ok": True, "updated": int(res.split()[-1])}


class EditIn(BaseModel):
    row: int
    column: str
    value: str
    remember: bool = True


@router.post("/runs/{run_id}/edit")
async def edit_cell(run_id: str, e: EditIn, ctx: Ctx = Depends(require("clean_data"))):
    r = await db.fetchrow("select r.upload_id, u.columns, u.mapping from cleaning_runs r join uploads u on u.id=r.upload_id where r.id=$1 and r.org_id=$2", run_id, ctx.org_id)
    if not r:
        raise HTTPException(404)
    d = await db.fetchrow("select raw_rows from upload_data where upload_id=$1", r["upload_id"])
    ci = r["columns"].index(e.column)
    old = d["raw_rows"][e.row][ci]
    old = "" if old is None else str(old)
    await db.execute("delete from cleaning_changes where run_id=$1 and row_index=$2 and column_name=$3", run_id, e.row, e.column)
    await db.execute("""insert into cleaning_changes(org_id,run_id,row_index,column_name,old_value,new_value,rule,category,confidence,status)
                        values($1,$2,$3,$4,$5,$6,'memory','memory',1,'approved')""", ctx.org_id, run_id, e.row, e.column, old, e.value)
    learned = False
    field = (r["mapping"].get(e.column) or {}).get("field")
    kind = kind_of(field)
    if e.remember and kind and old:
        await db.execute("""insert into cleaning_rules(org_id,column_kind,match_value,replace_value,created_by) values($1,$2,$3,$4,$5)
                            on conflict (org_id,column_kind,match_value) do update set replace_value=excluded.replace_value""", ctx.org_id, kind, old, e.value, ctx.user.id)
        learned = True
        await db.execute("""update cleaning_changes set new_value=$3, rule='memory', status='approved' where run_id=$1 and column_name=$2 and old_value=$4""",
                         run_id, e.column, e.value, old)
    return {"ok": True, "learned": learned}


def _materialize(headers, raw, changes):
    rows = [["" if v is None else str(v) for v in r] for r in raw]
    removed = set()
    for c in changes:
        if c["status"] == "rejected":
            continue
        if c["column_name"] == "*":
            removed.add(c["row_index"])
            continue
        ci = headers.index(c["column_name"])
        rows[c["row_index"]][ci] = c["new_value"] or ""
    return [r for i, r in enumerate(rows) if i not in removed]


def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@router.post("/runs/{run_id}/apply")
async def apply_run(run_id: str, ctx: Ctx = Depends(require("clean_data"))):
    run = await db.fetchrow("""select r.*, u.columns, u.mapping, u.entity, u.file_name from cleaning_runs r join uploads u on u.id=r.upload_id
                               where r.id=$1 and r.org_id=$2""", run_id, ctx.org_id)
    if not run:
        raise HTTPException(404)
    if run["imported_at"] and not run["reverted_at"]:
        raise HTTPException(409, "Already imported")
    d = await db.fetchrow("select raw_rows from upload_data where upload_id=$1", run["upload_id"])
    changes = await db.fetch("select * from cleaning_changes where run_id=$1", run_id)
    headers = run["columns"]
    rows = _materialize(headers, d["raw_rows"], changes)
    fmap = {(run["mapping"].get(h) or {}).get("field"): i for i, h in enumerate(headers) if (run["mapping"].get(h) or {}).get("field")}

    def g(r, f):
        i = fmap.get(f)
        return r[i].strip() if i is not None and i < len(r) and r[i] else None

    upload_id = run["upload_id"]
    entity = run["entity"]
    stats = {"sales": 0, "lines": 0, "customers": 0, "products_created": 0, "products_updated": 0}
    async with db.transaction() as c:
        branches = {match_key(b["name"]): b["id"] for b in await c.fetch("select id,name from branches where org_id=$1", ctx.org_id)}
        default_branch = next(iter(branches.values()), None)
        emps = {match_key(e["full_name"]): e["id"] for e in await c.fetch("select id, full_name from employees where org_id=$1", ctx.org_id)}
        prods = {match_key(p["name"]): dict(p) for p in await c.fetch("select id, name, cost, price from products where org_id=$1", ctx.org_id)}
        custs = {cu["phone"]: cu["id"] for cu in await c.fetch("select id, phone from customers where org_id=$1 and phone is not null", ctx.org_id)}

        async def product_id(name, price):
            k = match_key(name)
            if k in prods:
                return prods[k]["id"], prods[k]["cost"]
            pid = await c.fetchval("""insert into products(org_id,name,price,cost,upload_id) values($1,$2,$3,$4,$5) returning id""",
                                   ctx.org_id, name, price or 0, round((price or 0) * 0.75, 3), upload_id)
            prods[k] = {"id": pid, "name": name, "cost": round((price or 0) * 0.75, 3), "price": price}
            stats["products_created"] += 1
            return pid, prods[k]["cost"]

        if entity == "sales":
            sale_recs, item_recs = [], []
            groups = defaultdict(list)
            for i, r in enumerate(rows):
                key = g(r, "invoice_number") or f"{g(r, 'date')}-{g(r, 'cashier')}-{i // 3}"
                groups[key].append(r)
            for inv, lines in groups.items():
                r0 = lines[0]
                ds = g(r0, "date")
                try:
                    sold = dt.datetime.fromisoformat(ds) if ds else dt.datetime.now()
                except ValueError:
                    sold = dt.datetime.now()
                sold = sold.replace(tzinfo=dt.timezone(dt.timedelta(hours=3)))
                br = branches.get(match_key(g(r0, "branch") or ""), default_branch)
                emp = emps.get(match_key(g(r0, "cashier") or ""))
                cust = custs.get(g(r0, "phone") or "")
                items, subtotal = [], 0.0
                for r in lines:
                    name = g(r, "product")
                    q = _num(g(r, "quantity"))
                    p = _num(g(r, "unit_price"))
                    t = _num(g(r, "total"))
                    if not name or q is None or q <= 0 or q > 200:
                        continue
                    if p is None and t is not None:
                        p = t / q
                    if p is None:
                        continue
                    pid, cost = await product_id(name, p)
                    lt = round(q * p, 3)
                    subtotal += lt
                    items.append((pid, q, p, cost, lt))
                if not items:
                    continue
                sid = uuid.uuid4()
                pm = g(r0, "payment_method") or "cash"
                sale_recs.append((sid, uuid.UUID(str(ctx.org_id)), br, emp, cust, inv, sold, round(subtotal, 3), 0.0, round(subtotal - subtotal / 1.16, 3),
                                  round(subtotal, 3), pm if pm in ("cash", "card", "cliq", "wallet") else "cash", "completed", upload_id))
                item_recs.extend((uuid.uuid4(), uuid.UUID(str(ctx.org_id)), sid, pid, float(q), float(p), float(cost), 0.0, float(lt)) for pid, q, p, cost, lt in items)
                stats["sales"] += 1
                stats["lines"] += len(items)
            await c.copy_records_to_table("sales", records=sale_recs, columns=["id", "org_id", "branch_id", "employee_id", "customer_id", "invoice_number", "sold_at",
                                                                               "subtotal", "discount", "tax", "total", "payment_method", "status", "upload_id"])
            await c.copy_records_to_table("sale_items", records=item_recs, columns=["id", "org_id", "sale_id", "product_id", "quantity", "unit_price", "unit_cost", "discount", "line_total"])
        elif entity == "customers":
            for r in rows:
                name, phone = g(r, "customer_name"), g(r, "phone")
                if not name and not phone:
                    continue
                if phone and phone in custs:
                    continue
                cid = await c.fetchval("""insert into customers(org_id,full_name,phone,email,city,area,first_seen,upload_id) values($1,$2,$3,$4,$5,$6,current_date,$7) returning id""",
                                       ctx.org_id, name or phone, phone, g(r, "email"), g(r, "city"), g(r, "area"), upload_id)
                if phone:
                    custs[phone] = cid
                stats["customers"] += 1
        elif entity in ("products", "supplier_prices"):
            old_costs = []
            for r in rows:
                name = g(r, "product")
                if not name:
                    continue
                price = _num(g(r, "unit_price"))
                cost = _num(g(r, "cost"))
                if entity == "supplier_prices":
                    cost, price = price, None
                k = match_key(name)
                if k in prods:
                    if cost:
                        old_costs.append((str(prods[k]["id"]), float(prods[k]["cost"])))
                        await c.execute("update products set cost=$2 where id=$1", prods[k]["id"], cost)
                        stats["products_updated"] += 1
                else:
                    await product_id(name, price or (cost / 0.75 if cost else 0))
            stats["old_costs"] = old_costs
        learned = 0
        pairs = {(ch["column_name"], ch["old_value"], ch["new_value"]) for ch in changes if ch["rule"] in MERGE_RULES and ch["status"] != "rejected"}
        rule_recs = []
        for col, old, new in list(pairs)[:150]:
            kind = kind_of((run["mapping"].get(col) or {}).get("field"))
            if kind and old and new and match_key(old) != match_key(new):
                rule_recs.append((ctx.org_id, kind, old, new, ctx.user.id))
                learned += 1
        if rule_recs:
            await c.executemany("""insert into cleaning_rules(org_id,column_kind,match_value,replace_value,created_by) values($1,$2,$3,$4,$5)
                                   on conflict (org_id,column_kind,match_value) do update set times_applied = cleaning_rules.times_applied + 1""", rule_recs)
        await c.execute("update cleaning_changes set status='approved' where run_id=$1 and status='proposed'", run_id)
        imported = stats["sales"] or stats["customers"] or (stats["products_created"] + stats["products_updated"])
        await c.execute("update cleaning_runs set status='imported', imported_at=now(), reverted_at=null, stats = stats || $2 where id=$1",
                        run_id, {"import": {k: v for k, v in stats.items() if k != "old_costs"}, "learned_rules": learned, "old_costs": stats.get("old_costs", [])})
        await c.execute("update uploads set status='imported', imported_rows=$2 where id=$1", upload_id, imported)
    db.cache_clear()
    await db.audit(ctx.org_id, ctx.user.id, "cleaning.applied", "upload", str(upload_id), {"file": run["file_name"], **{k: v for k, v in stats.items() if k != "old_costs"}})
    await db.execute("insert into notifications(org_id,kind,title,link) values($1,'cleaning',$2,$3)", ctx.org_id,
                     f"{run['file_name']} cleaned & imported: {run['score_before']['score']:.0f} → {run['score_after']['score']:.0f}", f"/app/data/runs/{run_id}")
    return {"ok": True, "imported": {k: v for k, v in stats.items() if k != "old_costs"}, "learned_rules": learned}


@router.post("/runs/{run_id}/undo")
async def undo_run(run_id: str, ctx: Ctx = Depends(require("clean_data"))):
    run = await db.fetchrow("select * from cleaning_runs where id=$1 and org_id=$2", run_id, ctx.org_id)
    if not run or not run["imported_at"]:
        raise HTTPException(409, "Nothing to undo")
    async with db.transaction() as c:
        n1 = await c.execute("delete from sales where upload_id=$1 and org_id=$2", run["upload_id"], ctx.org_id)
        n2 = await c.execute("delete from customers where upload_id=$1 and org_id=$2", run["upload_id"], ctx.org_id)
        for pid, cost in (run["stats"] or {}).get("old_costs", []):
            await c.execute("update products set cost=$2 where id=$1 and org_id=$3", pid, cost, ctx.org_id)
        await c.execute("delete from products p where p.upload_id=$1 and p.org_id=$2 and not exists (select 1 from sale_items si where si.product_id=p.id)", run["upload_id"], ctx.org_id)
        await c.execute("update cleaning_runs set status='reverted', reverted_at=now() where id=$1", run_id)
        await c.execute("update uploads set status='cleaned', imported_rows=0 where id=$1", run["upload_id"])
    db.cache_clear()
    await db.audit(ctx.org_id, ctx.user.id, "cleaning.undone", "upload", str(run["upload_id"]))
    return {"ok": True, "sales_removed": int(n1.split()[-1]), "customers_removed": int(n2.split()[-1])}


@router.get("/rules")
async def rules(ctx: Ctx = Depends(require("view_dashboard"))):
    return await db.fetch("""select r.*, p.full_name created_by_name from cleaning_rules r left join profiles p on p.id=r.created_by
                             where r.org_id=$1 order by r.times_applied desc, r.created_at desc""", ctx.org_id)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, ctx: Ctx = Depends(require("clean_data"))):
    await db.execute("delete from cleaning_rules where id=$1 and org_id=$2", rule_id, ctx.org_id)
    return {"ok": True}

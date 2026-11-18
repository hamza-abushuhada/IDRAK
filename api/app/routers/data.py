import datetime as dt
import re
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import db
from ..auth import Ctx, require
from ..cleaning import engine
from ..cleaning import parsers as cleaning_parsers
from ..cleaning.arabic import match_key
from ..cleaning.context import load_context
from ..cleaning.fields import ENTITY_LABELS, FIELDS, LABELS, auto_map, detect_entity, kind_of
from ..cleaning.io import read_table
from ..services import ai

router = APIRouter(prefix="/data", tags=["data"])
MERGE_RULES = {"product_match", "person_match", "branch_map", "value_merge", "payment_map", "city_map"}


def _field_catalog():
    return [{"key": k, "kind": v[0], "en": LABELS[k][0], "ar": LABELS[k][1]} for k, v in FIELDS.items()]


async def _create_upload(ctx: Ctx, filename: str, data: bytes, source: str = "upload", batch_id: str | None = None):
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
    uid = await db.fetchval("""insert into uploads(org_id,uploaded_by,batch_id,file_name,file_size,source,entity,sheet_name,row_count,column_count,columns,mapping,status)
                               values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'mapped') returning id""",
                            ctx.org_id, ctx.user.id, batch_id, filename, len(data), source, entity, sheets[0] if sheets else None, len(rows), len(headers), headers, mapping)
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
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(413, "File too large for direct upload (max 4MB)")
    return await _create_upload(ctx, file.filename or "upload.csv", data)


def _column_values(upload: dict, field: str) -> list[str]:
    for index, header in enumerate(upload["columns"]):
        if (upload["mapping"].get(header) or {}).get("field") == field:
            return [str(row[index]).strip() for row in upload["raw_rows"] if index < len(row) and row[index] not in (None, "")]
    return []


def _column_index(upload: dict, field: str) -> int | None:
    return next((index for index, header in enumerate(upload["columns"])
                 if (upload["mapping"].get(header) or {}).get("field") == field), None)


def _valid_barcode(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return 8 <= len(digits) <= 14 and len(set(digits)) > 1


async def _build_batch_report(batch_id: str, org_id: str) -> dict:
    uploads = await db.fetch("""select u.id,u.file_name,u.entity,u.row_count,u.columns,u.mapping,d.raw_rows
                                from uploads u join upload_data d on d.upload_id=u.id
                                where u.batch_id=$1 and u.org_id=$2 order by u.created_at""", batch_id, org_id)
    catalog_names: set[str] = set()
    sales_names: set[str] = set()
    catalog_barcodes: dict[str, set[str]] = defaultdict(set)
    customer_phones: set[str] = set()
    sales_phones: set[str] = set()
    files = []

    for upload in uploads:
        files.append({k: upload[k] for k in ("id", "file_name", "entity", "row_count")})
        names = _column_values(upload, "product")
        if upload["entity"] in ("products", "supplier_prices"):
            catalog_names.update(match_key(v) for v in names if match_key(v))
            name_index = _column_index(upload, "product")
            barcode_index = _column_index(upload, "barcode")
            if name_index is not None and barcode_index is not None:
                for row in upload["raw_rows"]:
                    if name_index >= len(row) or barcode_index >= len(row):
                        continue
                    name, barcode = str(row[name_index] or "").strip(), str(row[barcode_index] or "").strip()
                    if name and _valid_barcode(barcode):
                        catalog_barcodes[re.sub(r"\D", "", barcode)].add(match_key(name))
        elif upload["entity"] == "sales":
            sales_names.update(match_key(v) for v in names if match_key(v))
            for value in _column_values(upload, "phone"):
                phone, _ = cleaning_parsers.parse_phone(value)
                if phone:
                    sales_phones.add(phone)
        elif upload["entity"] == "customers":
            for value in _column_values(upload, "phone"):
                phone, _ = cleaning_parsers.parse_phone(value)
                if phone:
                    customer_phones.add(phone)

    exact_products = sales_names & catalog_names
    unmatched_products = sales_names - catalog_names
    barcode_conflicts = sum(1 for names in catalog_barcodes.values() if len(names) > 1)
    warnings = []
    if sales_names and not catalog_names:
        warnings.append({"code": "missing_product_catalog", "count": len(sales_names)})
    if unmatched_products:
        warnings.append({"code": "unmatched_products", "count": len(unmatched_products)})
    if barcode_conflicts:
        warnings.append({"code": "barcode_conflicts", "count": barcode_conflicts})
    customer_matches = len(sales_phones & customer_phones)
    if sales_phones and customer_phones and customer_matches < len(sales_phones) * 0.5:
        warnings.append({"code": "low_customer_matches", "count": len(sales_phones) - customer_matches})
    unknown_files = sum(1 for upload in uploads if upload["entity"] == "unknown")
    if unknown_files:
        warnings.append({"code": "unknown_files", "count": unknown_files})

    rank = {"products": 1, "supplier_prices": 2, "customers": 3, "sales": 4, "unknown": 5}
    return {
        "files": files,
        "rows": sum(upload["row_count"] for upload in uploads),
        "recommended_order": [f["id"] for f in sorted(files, key=lambda f: rank.get(f["entity"], 5))],
        "relationships": {
            "sales_products": len(sales_names),
            "catalog_products": len(catalog_names),
            "exact_product_matches": len(exact_products),
            "unmatched_products": len(unmatched_products),
            "sales_customer_phones": len(sales_phones),
            "customer_phone_matches": customer_matches,
        },
        "review_samples": {"unmatched_products": sorted(unmatched_products)[:20]},
        "warnings": warnings,
    }


class BatchContract(BaseModel):
    currency: str = "JOD"
    price_unit: str = "jd"
    tax_mode: str = "none"
    tax_rate: Decimal | None = None
    date_order: str = "auto"
    unknown_values: str = "block"


@router.post("/batches")
async def create_batch(ctx: Ctx = Depends(require("upload_data"))):
    contract = BatchContract().model_dump(mode="json")
    batch_id = await db.fetchval("insert into import_batches(org_id,created_by,contract) values($1,$2,$3) returning id",
                                 ctx.org_id, ctx.user.id, contract)
    await db.audit(ctx.org_id, ctx.user.id, "batch.started", "import_batch", str(batch_id))
    return await get_batch(str(batch_id), ctx)


@router.post("/batches/{batch_id}/files")
async def add_batch_file(batch_id: str, file: UploadFile = File(...), ctx: Ctx = Depends(require("upload_data"))):
    batch = await db.fetchrow("select status from import_batches where id=$1 and org_id=$2", batch_id, ctx.org_id)
    if not batch:
        raise HTTPException(404, "Import batch not found")
    count = await db.fetchval("select count(*) from uploads where batch_id=$1 and org_id=$2", batch_id, ctx.org_id)
    if count >= 8:
        raise HTTPException(422, "A batch supports up to 8 files")
    name, data = file.filename or "upload.csv", await file.read()
    if not name.lower().endswith((".csv", ".txt", ".xlsx", ".xlsm")):
        raise HTTPException(422, "Batch supports CSV, TXT, XLSX and XLSM files")
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(413, "File too large for direct upload (max 4MB)")
    uploaded = await _create_upload(ctx, name, data, source="batch", batch_id=batch_id)
    report = await _build_batch_report(batch_id, ctx.org_id)
    await db.execute("update import_batches set link_report=$2,updated_at=now() where id=$1", batch_id, report)
    return uploaded


@router.post("/batches/{batch_id}/finalize")
async def finalize_batch(batch_id: str, ctx: Ctx = Depends(require("clean_data"))):
    count = await db.fetchval("select count(*) from uploads where batch_id=$1 and org_id=$2", batch_id, ctx.org_id)
    if count < 2:
        raise HTTPException(422, "An import batch needs at least two files")
    report = await _build_batch_report(batch_id, ctx.org_id)
    result = await db.execute("update import_batches set status='review',link_report=$3,updated_at=now() where id=$1 and org_id=$2",
                              batch_id, ctx.org_id, report)
    if result.endswith(" 0"):
        raise HTTPException(404, "Import batch not found")
    await db.audit(ctx.org_id, ctx.user.id, "batch.finalized", "import_batch", batch_id,
                   {"files": count, "rows": report["rows"]})
    return await get_batch(batch_id, ctx)


@router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    batch = await db.fetchrow("select * from import_batches where id=$1 and org_id=$2", batch_id, ctx.org_id)
    if not batch:
        raise HTTPException(404, "Import batch not found")
    batch["uploads"] = await db.fetch("""select id,file_name,entity,row_count,status,health_before,health_after
                                         from uploads where batch_id=$1 and org_id=$2 order by created_at""", batch_id, ctx.org_id)
    return batch


@router.put("/batches/{batch_id}/contract")
async def update_batch_contract(batch_id: str, contract: BatchContract, ctx: Ctx = Depends(require("clean_data"))):
    if contract.price_unit not in ("jd", "fils"):
        raise HTTPException(422, "price_unit must be jd or fils")
    if contract.tax_mode not in ("none", "from_file", "included", "excluded"):
        raise HTTPException(422, "Unsupported tax mode")
    if contract.date_order not in ("auto", "dmy", "mdy", "ymd"):
        raise HTTPException(422, "Unsupported date order")
    if contract.unknown_values not in ("block", "review"):
        raise HTTPException(422, "Unsupported unknown-value policy")
    if contract.tax_rate is not None and not Decimal("0") <= contract.tax_rate <= Decimal("100"):
        raise HTTPException(422, "tax_rate must be between 0 and 100")
    if contract.tax_mode in ("included", "excluded") and contract.tax_rate is None:
        raise HTTPException(422, "tax_rate is required for included or excluded tax")
    result = await db.execute("update import_batches set contract=$3,updated_at=now() where id=$1 and org_id=$2",
                              batch_id, ctx.org_id, contract.model_dump(mode="json"))
    if result.endswith(" 0"):
        raise HTTPException(404, "Import batch not found")
    return await get_batch(batch_id, ctx)


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
    return await db.fetch("""select u.id, u.batch_id, u.file_name, u.file_size, u.source, u.entity, u.row_count, u.column_count, u.status, u.health_before, u.health_after,
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
    u = await db.fetchrow("select mapping,batch_id from uploads where id=$1 and org_id=$2", upload_id, ctx.org_id)
    if not u:
        raise HTTPException(404)
    cur = u["mapping"] or {}
    for h, f in m.mapping.items():
        cur[h] = {**(cur.get(h) or {}), "field": f if f in FIELDS else None, "source": "user", "confidence": 1.0}
    entity = detect_entity({v["field"] for v in cur.values() if v.get("field")})
    await db.execute("update uploads set mapping=$3, entity=$4 where id=$1 and org_id=$2", upload_id, ctx.org_id, cur, entity)
    if u.get("batch_id"):
        report = await _build_batch_report(u["batch_id"], ctx.org_id)
        await db.execute("update import_batches set link_report=$2,updated_at=now() where id=$1", u["batch_id"], report)
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
    contract = {}
    if u.get("batch_id"):
        contract = await db.fetchval("select contract from import_batches where id=$1 and org_id=$2", u["batch_id"], ctx.org_id) or {}
    res = engine.run(headers, d["raw_rows"], mapping, ctxk,
                     price_unit=contract.get("price_unit", "jd"), date_order=contract.get("date_order", "auto"))
    memory_hits = sum(1 for c in res["changes"] if c["rule"] == "memory")
    blocking_reasons = {"missing_total", "total_mismatch", "invalid_date", "invalid_number",
                    "unknown_payment", "unknown_product", "missing_required", "future_date"}
    blocking_flags = [f for f in res["flags"] if f["reason"] in blocking_reasons]
    stats = {"rows_before": res["rows_before"], "rows_after": res["rows_after"], "issues": res["issues"], "clusters": res["clusters"],
             "flags": res["flags"][:500], "flag_count": len(res["flags"]),
             "blocking_flags": blocking_flags[:500], "blocking_flag_count": len(blocking_flags),
             "entity": res["entity"], "memory_hits": memory_hits,
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


def _money(v) -> Decimal | None:
    try:
        return Decimal(str(v)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None


class SkippedRow(Exception):
    """تُرفع داخليّاً لتخطّي صفّ واحد أثناء الاستيراد مع الاحتفاظ بالسبب.

    ترفع HTTPException كانت توقف الملف كاملاً عند أول غلط. SkippedRow
    تُلتقط في حلقة الصفوف، تُسجَّل، ويكمل الاستيراد.
    """

    def __init__(self, reason: str, reason_ar: str, row_index: int | None = None):
        self.reason = reason
        self.reason_ar = reason_ar
        self.row_index = row_index
        super().__init__(reason)


@router.post("/runs/{run_id}/apply")
async def apply_run(run_id: str, ctx: Ctx = Depends(require("clean_data"))):
    run = await db.fetchrow("""select r.*, u.columns, u.mapping, u.entity, u.file_name, u.batch_id, b.contract as batch_contract
                               from cleaning_runs r join uploads u on u.id=r.upload_id left join import_batches b on b.id=u.batch_id
                               where r.id=$1 and r.org_id=$2""", run_id, ctx.org_id)
    if not run:
        raise HTTPException(404)
    if run["imported_at"] and not run["reverted_at"]:
        raise HTTPException(409, "Already imported")
    d = await db.fetchrow("select raw_rows from upload_data where upload_id=$1", run["upload_id"])
    changes = await db.fetch("select * from cleaning_changes where run_id=$1", run_id)
    headers = run["columns"]
    rows = _materialize(headers, d["raw_rows"], changes)
    # Financial imports must be reconciled before they can affect reports.
    # Warnings remain reviewable; these conditions are unsafe to guess.
    if run["entity"] == "sales":
        approved_cells = {(c["row_index"], c["column_name"]) for c in changes
                          if c["status"] == "approved" and c["new_value"] not in (None, "")}
        blocked = [f for f in (run["stats"] or {}).get("blocking_flags", [])
                   if (f.get("row"), f.get("column")) not in approved_cells]
        if blocked:
            reasons = sorted({f["reason"] for f in blocked})
            raise HTTPException(422, f"Import blocked until financial issues are resolved: {', '.join(reasons)}")
    fmap = {(run["mapping"].get(h) or {}).get("field"): i for i, h in enumerate(headers) if (run["mapping"].get(h) or {}).get("field")}

    def g(r, f):
        i = fmap.get(f)
        return r[i].strip() if i is not None and i < len(r) and r[i] else None

    upload_id = run["upload_id"]
    entity = run["entity"]
    stats = {"sales": 0, "lines": 0, "customers": 0, "products_created": 0, "products_updated": 0}
    # الصفوف المتخطّاة: لا نرفض الملف، نجمعها ونعرضها للمستخدم.
    skipped: list[dict] = []

    def _skip(row_index: int | None, row_data, reason: str, reason_ar: str):
        snapshot = {}
        if row_data is not None:
            for h in headers:
                try:
                    val = row_data[headers.index(h)] if headers.index(h) < len(row_data) else ""
                    if val:
                        snapshot[h] = str(val)[:120]
                except (ValueError, IndexError):
                    continue
        skipped.append({"row": row_index, "reason": reason, "reason_ar": reason_ar, "data": snapshot})
    async with db.transaction() as c:
        branches = {match_key(b["name"]): b["id"] for b in await c.fetch("select id,name from branches where org_id=$1", ctx.org_id)}
        emps = {match_key(e["full_name"]): e["id"] for e in await c.fetch("select id, full_name from employees where org_id=$1", ctx.org_id)}
        product_rows = [dict(p) for p in await c.fetch("select id,name,cost,price,barcode,sku from products where org_id=$1", ctx.org_id)]
        names: dict[str, list[dict]] = defaultdict(list)
        barcodes: dict[str, list[dict]] = defaultdict(list)
        for product in product_rows:
            names[match_key(product["name"])].append(product)
            if product["barcode"] and _valid_barcode(product["barcode"]):
                barcodes[re.sub(r"\D", "", product["barcode"])].append(product)
        custs = {cu["phone"]: cu["id"] for cu in await c.fetch("select id, phone from customers where org_id=$1 and phone is not null", ctx.org_id)}

        def find_product(name, barcode=None):
            if barcode and _valid_barcode(barcode):
                matches = barcodes.get(re.sub(r"\D", "", barcode), [])
                return matches[0] if len(matches) == 1 else None
            matches = names.get(match_key(name), [])
            return matches[0] if len(matches) == 1 else None

        async def product_id(name, price, cost=None, barcode=None, sku=None):
            k = match_key(name)
            existing = find_product(name, barcode)
            if existing:
                if k != match_key(existing["name"]):
                    await c.execute("""insert into product_aliases(org_id,product_id,alias,source)
                                       select $1,$2,$3,'import' where not exists
                                       (select 1 from product_aliases where org_id=$1 and product_id=$2 and alias=$3)""",
                                    ctx.org_id, existing["id"], name)
                return existing["id"], existing["cost"]
            if cost is None:
                raise SkippedRow(
                    f"Unknown product has no cost: {name}. Add it to the catalog or include a cost column",
                    f"صنف جديد بدون تكلفة: {name}. أضفه للكتالوج أو ضمّن عمود تكلفة",
                )
            cost = _money(cost)
            if cost is None or cost < 0:
                raise SkippedRow(
                    f"Invalid cost for new product: {name}",
                    f"تكلفة غير صالحة لصنف جديد: {name}",
                )
            stored_barcode = re.sub(r"\D", "", barcode) if barcode and _valid_barcode(barcode) else None
            pid = await c.fetchval("""insert into products(org_id,name,sku,barcode,price,cost,upload_id) values($1,$2,$3,$4,$5,$6,$7) returning id""",
                                   ctx.org_id, name, sku, stored_barcode, price or 0, cost, upload_id)
            product = {"id": pid, "name": name, "cost": cost, "price": price, "barcode": stored_barcode, "sku": sku}
            names[k].append(product)
            if stored_barcode:
                barcodes[stored_barcode].append(product)
            stats["products_created"] += 1
            return pid, cost

        if entity == "sales":
            sale_recs, item_recs = [], []
            groups = defaultdict(list)
            for ri, r in enumerate(rows):
                invoice = g(r, "invoice_number")
                if not invoice:
                    _skip(ri, r, "Row has no invoice number",
                          "الصفّ بدون رقم فاتورة")
                    continue
                key = (invoice, (g(r, "date") or "")[:10], match_key(g(r, "branch") or ""))
                groups[key].append((ri, r))
            for _, lines in groups.items():
                ri0, r0 = lines[0]
                try:
                    inv = g(r0, "invoice_number")
                    ds = g(r0, "date")
                    if not ds:
                        raise SkippedRow(f"Invoice {inv} has no date",
                                         f"الفاتورة {inv} بدون تاريخ", ri0)
                    try:
                        sold = dt.datetime.fromisoformat(ds)
                    except ValueError as exc:
                        raise SkippedRow(f"Invoice {inv} has an invalid date: {ds}",
                                         f"الفاتورة {inv} فيها تاريخ غير صالح: {ds}", ri0) from exc
                    sold = sold.replace(tzinfo=dt.timezone(dt.timedelta(hours=3)))
                    branch_name = g(r0, "branch")
                    br = branches.get(match_key(branch_name or ""))
                    if branch_name and br is None:
                        raise SkippedRow(f"Unknown branch: {branch_name}",
                                         f"فرع غير معروف: {branch_name}", ri0)
                    emp = emps.get(match_key(g(r0, "cashier") or ""))
                    cust = custs.get(g(r0, "phone") or "")
                    items, subtotal = [], Decimal("0")
                    for _ri, r in lines:
                        name = g(r, "product")
                        q = _num(g(r, "quantity"))
                        p = _num(g(r, "unit_price"))
                        t = _num(g(r, "total"))
                        cost = _num(g(r, "cost"))
                        if not name or q is None or q <= 0 or q > 200:
                            continue
                        if p is None and t is not None:
                            p = t / q
                        if p is None:
                            continue
                        price = _money(p)
                        if price is None:
                            raise SkippedRow(f"Invoice {inv}: invalid unit price {p}",
                                             f"الفاتورة {inv}: سعر وحدة غير صالح {p}", ri0)
                        pid, cost = await product_id(name, price, cost, g(r, "barcode"), g(r, "sku"))
                        lt = (Decimal(str(q)) * price).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                        subtotal += lt
                        items.append((pid, Decimal(str(q)), price, cost, lt))
                    if not items:
                        continue
                    sid = uuid.uuid4()
                    pm = g(r0, "payment_method")
                    if pm not in ("cash", "card", "cliq", "wallet"):
                        raise SkippedRow(f"Invoice {inv}: unknown or missing payment method ({pm or 'empty'})",
                                         f"الفاتورة {inv}: طريقة دفع غير معروفة أو مفقودة ({pm or 'فارغ'})", ri0)
                    contract = run["batch_contract"] or {}
                    discount = _money(g(r0, "discount") or 0) or Decimal("0")
                    tax_mode = contract.get("tax_mode", "none")
                    rate = Decimal(str(contract.get("tax_rate") or 0)) / Decimal("100")
                    if tax_mode == "from_file":
                        tax = _money(g(r0, "tax"))
                        if tax is None:
                            raise SkippedRow(f"Invoice {inv} is missing its tax value",
                                             f"الفاتورة {inv} ينقصها قيمة الضريبة", ri0)
                        net_subtotal, total = subtotal, subtotal - discount + tax
                    elif tax_mode == "excluded":
                        net_subtotal = subtotal
                        tax = ((subtotal - discount) * rate).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                        total = subtotal - discount + tax
                    elif tax_mode == "included":
                        gross = subtotal - discount
                        tax = (gross - gross / (Decimal("1") + rate)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP) if rate else Decimal("0")
                        net_subtotal = gross - tax + discount
                        total = gross
                    else:
                        net_subtotal, tax, total = subtotal, Decimal("0"), subtotal - discount
                    sale_recs.append((sid, uuid.UUID(str(ctx.org_id)), br, emp, cust, inv, sold, net_subtotal, discount, tax,
                                      total, pm, "completed", upload_id))
                    item_recs.extend((uuid.uuid4(), uuid.UUID(str(ctx.org_id)), sid, pid, q, p, cost, Decimal("0"), lt) for pid, q, p, cost, lt in items)
                    stats["sales"] += 1
                    stats["lines"] += len(items)
                except SkippedRow as exc:
                    _skip(exc.row_index if exc.row_index is not None else ri0, r0, exc.reason, exc.reason_ar)
                    continue
            if sale_recs:
                await c.copy_records_to_table("sales", records=sale_recs, columns=["id", "org_id", "branch_id", "employee_id", "customer_id", "invoice_number", "sold_at",
                                                                                   "subtotal", "discount", "tax", "total", "payment_method", "status", "upload_id"])
                await c.copy_records_to_table("sale_items", records=item_recs, columns=["id", "org_id", "sale_id", "product_id", "quantity", "unit_price", "unit_cost", "discount", "line_total"])
        elif entity == "customers":
            for ri, r in enumerate(rows):
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
            for ri, r in enumerate(rows):
                name = g(r, "product")
                if not name:
                    continue
                price = _num(g(r, "unit_price"))
                cost = _num(g(r, "cost"))
                if entity == "supplier_prices":
                    cost, price = (cost if cost is not None else price), None
                existing = find_product(name, g(r, "barcode"))
                if existing:
                    if cost:
                        old_costs.append((str(existing["id"]), float(existing["cost"])))
                        await c.execute("update products set cost=$2 where id=$1", existing["id"], cost)
                        stats["products_updated"] += 1
                else:
                    try:
                        await product_id(name, price or 0, cost, g(r, "barcode"), g(r, "sku"))
                    except SkippedRow as exc:
                        _skip(ri, r, exc.reason, exc.reason_ar)
                        continue
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
        # نُخزّن الصفوف المتخطّاة في stats حتى يقدر المستخدم ينزّلها كـ CSV.
        # قد تكون كبيرة، فنقصّها على 500 سبب مع عدّاد كلّي.
        skipped_blob = {"count": len(skipped), "items": skipped[:500]}
        await c.execute("update cleaning_runs set status='imported', imported_at=now(), reverted_at=null, stats = stats || $2 where id=$1",
                        run_id, {"import": {k: v for k, v in stats.items() if k != "old_costs"}, "learned_rules": learned, "old_costs": stats.get("old_costs", []),
                                 "skipped": skipped_blob})
        await c.execute("update uploads set status='imported', imported_rows=$2 where id=$1", upload_id, imported)
    db.cache_clear()
    await db.audit(ctx.org_id, ctx.user.id, "cleaning.applied", "upload", str(upload_id), {"file": run["file_name"], "skipped": len(skipped),
                                                                                           **{k: v for k, v in stats.items() if k != "old_costs"}})
    await db.execute("insert into notifications(org_id,kind,title,link) values($1,'cleaning',$2,$3)", ctx.org_id,
                     f"{run['file_name']} cleaned & imported: {run['score_before']['score']:.0f} → {run['score_after']['score']:.0f}", f"/app/data/runs/{run_id}")
    return {"ok": True, "imported": {k: v for k, v in stats.items() if k != "old_costs"}, "learned_rules": learned,
            "skipped": {"count": len(skipped), "sample": skipped[:20]}}


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


@router.get("/runs/{run_id}/skipped.csv")
async def skipped_csv(run_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    """تنزيل الصفوف المتخطّاة أثناء الاستيراد كـ CSV ليصلحها المستخدم ويرفعها.

    أول الملفّ سبب لكل صفّ، ثم أعمدة الصفّ كما كانت. يتولّد مرة
    وحدة بعد الـ apply، فلا يرهق قاعدة البيانات.
    """
    import csv
    import io

    from fastapi.responses import StreamingResponse

    run = await db.fetchrow(
        "select stats, (select file_name from uploads where id=upload_id) fn from cleaning_runs where id=$1 and org_id=$2",
        run_id, ctx.org_id)
    if not run:
        raise HTTPException(404)
    items = ((run["stats"] or {}).get("skipped") or {}).get("items") or []
    cols = []
    seen = set()
    for it in items:
        for k in (it.get("data") or {}).keys():
            if k not in seen:
                seen.add(k)
                cols.append(k)
    buf = io.StringIO()
    # BOM لإكسل العربي.
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["row_index", "reason_ar", "reason_en", *cols])
    for it in items:
        data = it.get("data") or {}
        w.writerow([it.get("row", ""), it.get("reason_ar", ""), it.get("reason", ""),
                    *(data.get(c, "") for c in cols)])
    buf.seek(0)
    fn = (run["fn"] or "import").rsplit(".", 1)[0]
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"content-disposition": f'attachment; filename="skipped_{fn}.csv"'})


@router.get("/rules")
async def rules(ctx: Ctx = Depends(require("view_dashboard"))):
    return await db.fetch("""select r.*, p.full_name created_by_name from cleaning_rules r left join profiles p on p.id=r.created_by
                             where r.org_id=$1 order by r.times_applied desc, r.created_at desc""", ctx.org_id)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, ctx: Ctx = Depends(require("clean_data"))):
    await db.execute("delete from cleaning_rules where id=$1 and org_id=$2", rule_id, ctx.org_id)
    return {"ok": True}

from functools import lru_cache
import datetime as dt
import logging
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
from ..cleaning.arabic import match_key, place_key
from ..cleaning.context import KIND_ALIAS, load_context
from ..cleaning import learning, referee
from ..cleaning.fields import (ENTITIES, ENTITY_KEY, ENTITY_LABELS, FIELDS, LABELS, NEEDS, auto_map,
                               entity_state, field_signature, kind_of)
from ..cleaning.io import read_table
from ..services import ai

router = APIRouter(prefix="/data", tags=["data"])
log = logging.getLogger(__name__)
MERGE_RULES = {"product_match", "person_match", "branch_map", "value_merge", "payment_map", "city_map"}


def _field_catalog():
    return [{"key": k, "kind": v[0], "en": LABELS[k][0], "ar": LABELS[k][1]} for k, v in FIELDS.items()]


async def _ai_referee(ctx: Ctx, headers: list[str], rows: list[list], mapping: dict[str, dict],
                      skip: set[str]) -> dict[str, dict]:
    """Let the AI referee the uncertain columns (cleaning/referee.py). Fails open.

    Goes through the org's daily AI budget like the assistant: over the cap, the
    mapping stays as the rules left it. The call's cost is tracked by ai.track().
    """
    if not ai.available() or not referee.candidates(headers, mapping, skip):
        return mapping
    if not await ai.budget_reserve(ctx.org_id):
        return mapping
    try:
        return await referee.arbitrate(
            headers, rows, mapping,
            lambda judge, decided: ai.map_columns(judge, decided, ctx.org_id, ctx.user.id), skip=skip)
    finally:
        await ai.budget_release(ctx.org_id)


# ── Phase 3: what companies confirmed (cleaning/learning.py). Every DB step
# here fails open: on any error the mapping works exactly as it did before. ──

_SHARED_TTL = 600  # seconds; a newly promoted header reaches uploads within 10 minutes
# Counts only, never which org voted: header, field, how many orgs and users
# chose it, and how many orgs voted on the header at all. Demo orgs don't count.
_SHARED_SQL = """select header_key, field, orgs, voters, total from (
                   select v.header_key, v.field, count(*) orgs, count(distinct v.voted_by) voters,
                          sum(count(*)) over (partition by v.header_key) total
                     from mapping_votes v join organizations o on o.id = v.org_id
                    where not o.is_demo
                    group by v.header_key, v.field) t
                  where orgs >= $1"""


async def _shared_synonyms() -> dict[str, str]:
    """header_key -> field that enough companies agree on; cached, {} on any error."""
    hit = db.cache_get(("shared_synonyms",), _SHARED_TTL)
    if hit is not None:
        return hit
    try:
        shared = learning.promote(await db.fetch(_SHARED_SQL, learning.MIN_ORGS))
    except Exception:
        log.warning("shared synonyms unavailable", exc_info=True)
        shared = {}  # cached too, so a missing table isn't queried on every upload
    return db.cache_set(("shared_synonyms",), shared)


async def _record_votes(ctx: Ctx, votes: list[tuple[str, str]]) -> None:
    """One vote per org per header (an org changing its mind replaces its vote)."""
    if not votes:
        return
    try:
        async with db.transaction() as c:
            await c.executemany("""insert into mapping_votes(org_id,header_key,field,voted_by) values($1,$2,$3,$4)
                                   on conflict (org_id,header_key) do update
                                   set field=excluded.field, voted_by=excluded.voted_by, updated_at=now()""",
                                [(ctx.org_id, k, f, ctx.user.id) for k, f in votes])
    except Exception:
        log.warning("mapping votes not saved", exc_info=True)


async def _load_file_memory(org_id: str, headers: list[str]) -> dict | None:
    fp = learning.fingerprint(headers)
    if fp is None:
        return None
    try:
        return await db.fetchrow("select columns, entity, signature, confirmed_by from mapping_fingerprints"
                                 " where org_id=$1 and fingerprint=$2", org_id, fp)
    except Exception:
        log.warning("file memory unavailable", exc_info=True)
        return None


async def _remember_file(ctx: Ctx, headers: list[str], rows: list[list], mapping: dict, state: dict) -> None:
    """Save this file's confirmed mapping and type under its fingerprint (cleaning/learning.py)."""
    try:
        rec = learning.file_memory(headers, rows, mapping, state)
        if rec is None:
            return
        fp, saved = rec
        await db.execute("""insert into mapping_fingerprints(org_id,fingerprint,columns,entity,signature,confirmed_by)
                            values($1,$2,$3,$4,$5,$6)
                            on conflict (org_id,fingerprint) do update
                            set columns=excluded.columns, entity=excluded.entity, signature=excluded.signature,
                                confirmed_by=excluded.confirmed_by, updated_at=now()""",
                         ctx.org_id, fp, saved["columns"], saved["entity"], saved["signature"],
                         ctx.user.id if saved["entity"] else None)
    except Exception:
        log.warning("file memory not saved", exc_info=True)


_BLOCKED = ("Confirm the file type first: Idrak isn't sure what this file is "
            "(sales, customers, products, supplier prices or a generic table). "
            "Choose it on the column mapping step, then clean again.")


async def _create_upload(ctx: Ctx, filename: str, data: bytes, source: str = "upload", batch_id: str | None = None):
    try:
        headers, rows, sheets = read_table(filename, data)
    except Exception as e:
        raise HTTPException(422, f"Could not read this file: {e}") from e
    if not headers:
        raise HTTPException(422, "No header row found")
    if ENTITY_KEY in headers:
        raise HTTPException(422, f"A column can't be named {ENTITY_KEY}")
    # بصمة الملف: نفس أعمدة ملف نظّفته الشركة قبل؟ ربطه المؤكَّد بيرجع فوراً
    # (source=memory, via=file) بلا ذكاء اصطناعي، والقيم بتنفحص: عمود تغيّرت
    # قيمه عن آخر مرة بيرجع أصفر للمراجعة.
    saved = await _load_file_memory(ctx.org_id, headers)
    from_file = learning.apply_file_memory(headers, rows, saved) if saved else None
    if from_file:
        mapping, explicit_unused = from_file
    else:
        # نمرّر الصفوف: الربط يعتمد على اسم العمود وعلى شكل قيمه معاً، والأعمدة
        # الضعيفة تُعلَّم "review" فيطلب منها الواجهة تأكيداً قبل التنظيف.
        # والأسماء اللي أكّدتها ≥3 شركات (مرادفات مشتركة) بتنقرأ قبل التقريبية.
        mapping = auto_map(headers, rows, shared=await _shared_synonyms())
        # ربط الأعمدة اللي عدّله المستخدم قبل تنحفظ كقواعد، فملف الشهر الجاي
        # من نفس نظام الكاشير بينربط لحاله. القيمة الفاضية = "لا تستخدم"
        # صراحةً، فما نخلّي الذكاء الاصطناعي يرجّعها.
        remembered = {r["match_value"]: (r["replace_value"] or "")
                      for r in await db.fetch(
                          "select match_value, replace_value from cleaning_rules"
                          " where org_id=$1 and column_kind='column'", ctx.org_id)}
        explicit_unused = set()
        used_rules = [h for h in headers if h in remembered]
        if used_rules:
            # The "applied" counter on the data page; it only moved when a rule was re-learned.
            await db.execute("update cleaning_rules set times_applied = times_applied + 1"
                             " where org_id=$1 and column_kind='column' and match_value = any($2::text[])",
                             ctx.org_id, used_rules)
        for h in headers:
            if h not in remembered:
                continue
            want = remembered[h]
            if want == "":
                mapping[h] = {"field": None, "confidence": 1.0, "source": "memory"}
                explicit_unused.add(h)
            elif want in FIELDS:
                mapping[h] = {"field": want, "confidence": 1.0, "source": "memory"}
        seen_fields: set[str] = set()
        for h in headers:
            f = mapping[h]["field"]
            if f and f in seen_fields:
                mapping[h] = {"field": None, "confidence": 0.0, "source": None}
            elif f:
                seen_fields.add(f)
    # الذكاء الاصطناعي حَكَم: يُسأل عن الأعمدة الفاضية والمعلّمة "review"
    # فقط، وما بيغيّر عموداً متأكدين منه (cleaning/referee.py). بياخد ثواني
    # وأحياناً يعلّق والرفع كله واقف عليه، فمهلته قصيرة؛ تأخّر أو فشل،
    # نكمّل بالربط كما هو وبنفس علامات المراجعة.
    mapping = await _ai_referee(ctx, headers, rows, mapping, explicit_unused)
    # نوع الملف المؤكَّد على آخر ملف بنفس الأعمدة بينتقل، بس إذا ولا عمود
    # رجع للمراجعة وكل عمود محافظ على حقله (نفس قاعدة field_signature).
    if from_file and (carried := learning.carried_entity(headers, mapping, saved)):
        mapping[ENTITY_KEY] = carried
    entity = entity_state(headers, mapping)["entity"]
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


# المضيفات المسموح بها للوجهة النهائية بعد إعادة التوجيه. الرابط الأصلي مثبّت
# على docs.google.com، لكن export يعيد التوجيه أحياناً إلى googleusercontent.com.
# نتحقّق أن الرحلة كلها تبقى داخل جوجل كدفاع عمق ضد إساءة إعادة التوجيه للوصول
# لموارد داخلية (SSRF).
_SHEET_HOST_SUFFIXES = (".google.com", ".googleusercontent.com")


@router.post("/import-url")
async def import_url(u: UrlIn, ctx: Ctx = Depends(require("upload_data"))):
    m = re.search(r"docs\.google\.com/spreadsheets/d/([\w-]+)", u.url)
    if not m:
        raise HTTPException(422, "Paste a Google Sheets share link (Anyone with the link can view)")
    gid = re.search(r"gid=(\d+)", u.url)
    url = f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, max_redirects=5) as cx:
            r = await cx.get(url)
    except httpx.HTTPError as e:
        # خطأ شبكة أو تجاوز لعدد إعادات التوجيه: نردّ 422 لطيفة بدل 500.
        raise HTTPException(422, "Couldn't open the sheet. Make sure sharing is set to 'Anyone with the link'.") from e
    final_host = (r.url.host or "").lower()
    if not any(final_host.endswith(s) for s in _SHEET_HOST_SUFFIXES):
        raise HTTPException(422, "Couldn't open the sheet (unexpected redirect).")
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
    d = await db.fetchrow(
        "select (select coalesce(jsonb_agg(e), '[]'::jsonb)"
        "          from (select e from jsonb_array_elements(raw_rows) e limit 25) t) preview"
        " from upload_data where upload_id=$1", upload_id)
    u["preview"] = (d["preview"] if d else []) or []
    u["fields"] = _field_catalog()
    # نوع الملف: المكتشف، أسباب طلب التأكيد، وتأكيد المستخدم إن وُجد.
    u["entity_check"] = entity_state(u["columns"] or [], u["mapping"])
    u["mapping"] = {h: m for h, m in (u["mapping"] or {}).items() if h != ENTITY_KEY}
    u["entities"] = {k: {"en": v[0], "ar": v[1], "needs": NEEDS[k]} for k, v in ENTITY_LABELS.items()}
    u["entity_label"] = ENTITY_LABELS.get(u["entity"], ENTITY_LABELS["unknown"])
    u["last_run_id"] = await db.fetchval("select id from cleaning_runs where upload_id=$1 order by started_at desc limit 1", upload_id)
    return u


class MappingIn(BaseModel):
    mapping: dict[str, str | None]
    # نوع الملف اللي أكّده أو اختاره المستخدم (sales / customers / ...).
    entity: str | None = None


@router.put("/uploads/{upload_id}/mapping")
async def set_mapping(upload_id: str, m: MappingIn, ctx: Ctx = Depends(require("upload_data"))):
    u = await db.fetchrow("select columns,mapping,batch_id from uploads where id=$1 and org_id=$2", upload_id, ctx.org_id)
    if not u:
        raise HTTPException(404)
    if m.entity is not None and m.entity not in ENTITIES:
        raise HTTPException(422, f"Unknown file type: {m.entity}")
    headers = u["columns"] or []
    cur = u["mapping"] or {}
    before = {h: dict(cur.get(h) or {}) for h in headers}  # as the screen showed it, for the shared votes
    learned = []
    for h, f in m.mapping.items():
        # أعمدة الملف فقط: مفتاح غريب (مثل مفتاح تأكيد النوع) لا يُكتب ولا يُحفظ كقاعدة.
        if h not in headers:
            continue
        cur[h] = {**(cur.get(h) or {}), "field": f if f in FIELDS else None, "source": "user", "confidence": 1.0,
                  "review": False, "evidence": None}
        # نحفظ اختيار المستخدم لاسم العمود نفسه، فيرجع يتطبّق تلقائياً
        # على كل ملف جاي من نفس نظام الكاشير.
        learned.append((ctx.org_id, "column", h, f if f in FIELDS else "", ctx.user.id))
    if learned:
        async with db.transaction() as c:
            await c.executemany("""insert into cleaning_rules(org_id,column_kind,match_value,replace_value,created_by)
                                   values($1,$2,$3,$4,$5)
                                   on conflict (org_id,column_kind,match_value) do update set replace_value=excluded.replace_value""", learned)
    if m.entity is not None:
        # التأكيد مربوط بهذا الربط بالذات: لو تغيّر عمود بعدين، يُطلب من جديد.
        cur[ENTITY_KEY] = {"entity": m.entity, "fields": field_signature({h: cur.get(h) or {} for h in headers}),
                           "by": str(ctx.user.id), "at": dt.datetime.now(dt.timezone.utc).isoformat()}
    state = entity_state(headers, cur)
    entity = state["entity"]
    await db.execute("update uploads set mapping=$3, entity=$4 where id=$1 and org_id=$2", upload_id, ctx.org_id, cur, entity)
    if u.get("batch_id"):
        report = await _build_batch_report(u["batch_id"], ctx.org_id)
        await db.execute("update import_batches set link_report=$2,updated_at=now() where id=$1", u["batch_id"], report)
    # الأعمدة اللي المستخدم غيّرها أو أكّدها وهي صفراء = صوت لهالشركة على
    # اسم العمود المطبَّع. ≥3 شركات متفقة → مرادف مشترك للكل (learning.py).
    await _record_votes(ctx, learning.votes(headers, before, m.mapping))
    return {"ok": True, "entity": entity, "entity_check": state}


@router.post("/uploads/{upload_id}/clean")
async def clean(upload_id: str, ctx: Ctx = Depends(require("clean_data"))):
    u = await db.fetchrow("select * from uploads where id=$1 and org_id=$2", upload_id, ctx.org_id)
    d = await db.fetchrow("select raw_rows from upload_data where upload_id=$1", upload_id)
    if not u or not d:
        raise HTTPException(404, "Upload data not found")
    headers = u["columns"]
    # التنظيف يعمل داخل الطلب. الملفات الكبيرة جداً تتجاوز مهلة الاستضافة
    # فيقطع الاتصال برسالة "network" بلا تفسير. نرفض بلطف ونطلب التقسيم.
    if len(d["raw_rows"]) > 120000:
        raise HTTPException(413, f"This file has {len(d['raw_rows']):,} rows. Idrak cleans up to 120,000 rows per file — "
                                 f"split it by month (e.g. one file per month) and upload them separately.")
    # نوع ملف غير مؤكَّد (مشتريات بشكل مبيعات، سجل هدر، أعمدة ناقصة...) لا
    # يُنظَّف حتى يؤكّده المستخدم. الواجهة تمنع الزر، وهذا يمنع أي مسار آخر.
    state = entity_state(headers, u["mapping"])
    if state["blocked"]:
        raise HTTPException(409, _BLOCKED)
    mapping = {h: ((u["mapping"] or {}).get(h) or {}).get("field") for h in headers}
    ctxk = await load_context(ctx.org_id)
    contract = {}
    if u.get("batch_id"):
        contract = await db.fetchval("select contract from import_batches where id=$1 and org_id=$2", u["batch_id"], ctx.org_id) or {}
    res = engine.run(headers, d["raw_rows"], mapping, ctxk,
                     price_unit=contract.get("price_unit", "jd"), date_order=contract.get("date_order", "auto"),
                     entity=state["entity"])
    memory_hits = sum(1 for c in res["changes"] if c["rule"] == "memory")
    # الصنف غير الموجود ليس سبباً لتخطّي الصف: الاستيراد ينشئه.
    # كان هنا فكانت كل صفوف ملف فيه أصناف جديدة تُتخطّى.
    blocking_reasons = {"missing_total", "total_mismatch", "invalid_date", "invalid_number",
                    "unknown_payment", "missing_required", "future_date"}
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
    # الربط والنوع صاروا مؤكَّدين: نحفظهم تحت بصمة الملف للمرة الجاية.
    await _remember_file(ctx, headers, d["raw_rows"], u["mapping"] or {}, state)
    return await get_run(str(run_id), ctx)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, ctx: Ctx = Depends(require("view_dashboard"))):
    r = await db.fetchrow("""select r.*, u.file_name, u.columns, u.mapping, u.row_count, u.entity from cleaning_runs r join uploads u on u.id=r.upload_id
                             where r.id=$1 and r.org_id=$2""", run_id, ctx.org_id)
    if not r:
        raise HTTPException(404, "Run not found")
    r["mapping"] = {h: m for h, m in (r["mapping"] or {}).items() if h != ENTITY_KEY}
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


@lru_cache(maxsize=200_000)
def _num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _rowcount(res) -> int:
    """صيغة asyncpg لنتيجة execute: "DELETE 12" → 12."""
    try:
        return int(str(res).split()[-1])
    except (ValueError, IndexError):
        return 0


@lru_cache(maxsize=200_000)
def _money(v) -> Decimal | None:
    # Decimal(str(v)) من أغلى العمليات بالحلقة، والقيم نفسها تتكرر بكل سطر.
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
    # نفس حارس clean: تشغيلات قديمة (قبل هذا الحارس) أو ربط تغيّر بعد التنظيف.
    if entity_state(run["columns"] or [], run["mapping"])["blocked"]:
        raise HTTPException(409, _BLOCKED)
    cleaned_as = (run["stats"] or {}).get("entity")
    if cleaned_as and cleaned_as != run["entity"]:
        raise HTTPException(409, "The file type changed after this file was cleaned. Clean it again before importing.")
    d = await db.fetchrow("select raw_rows from upload_data where upload_id=$1", run["upload_id"])
    changes = await db.fetch("select * from cleaning_changes where run_id=$1", run_id)
    headers = run["columns"]
    rows = _materialize(headers, d["raw_rows"], changes)
    # _materialize تحذف الصفوف المعلَّمة بالحذف، فترقيم rows ما يطابق
    # ترقيم الملف الأصلي. نحتاج الخريطة لأن أعلام المشاكل المالية
    # مسجّلة بترقيم الملف الأصلي.
    _removed_idx = {c["row_index"] for c in changes
                    if c["column_name"] == "*" and c["status"] != "rejected"}
    row_map = [i for i in range(len(d["raw_rows"])) if i not in _removed_idx]
    # الصفوف اللي فيها مشكلة مالية (تاريخ مستقبلي، إجمالي ناقص، إجمالي
    # ما يطابق الكمية×السعر...) كانت توقف الملف كامل بـ 422 ولا في طريقة
    # لإكمالها من الواجهة — الشاشة تعرض "فشل الاستيراد" وبس.
    # الحين: الصفوف المتأثرة تُتخطّى وتظهر بقائمة الصفوف المتخطّاة مع
    # السبب، وباقي الملف ينستورد. لو كانت كلها فيها مشاكل، النتيجة
    # imported=0 مع القائمة كاملة — أوضح من رسالة خطأ بلا مخرج.
    blocked_reasons: dict[int, tuple[str, str]] = {}
    if run["entity"] == "sales":
        approved_cells = {(c["row_index"], c["column_name"]) for c in changes
                          if c["status"] == "approved" and c["new_value"] not in (None, "")}
        reason_labels = {
            "missing_total": ("Line total is missing", "إجمالي السطر ناقص"),
            "total_mismatch": ("Line total does not match quantity × unit price",
                               "إجمالي السطر لا يطابق الكمية × سعر الوحدة"),
            "invalid_date": ("Date can't be read", "تاريخ غير مفهوم"),
            "invalid_number": ("Number can't be read", "رقم غير مفهوم"),
            "unknown_payment": ("Unknown payment method", "طريقة دفع غير معروفة"),
            "unknown_product": ("Product not in your catalog", "صنف غير موجود بقائمتك"),
            "missing_required": ("A required value is missing", "قيمة أساسية ناقصة"),
            "future_date": ("Date is in the future", "تاريخ بالمستقبل"),
        }
        for f in (run["stats"] or {}).get("blocking_flags", []):
            if (f.get("row"), f.get("column")) in approved_cells:
                continue
            entry = reason_labels.get(f.get("reason"), (f.get("reason"), f.get("reason")))
            blocked_reasons.setdefault(f.get("row"), entry)
    fmap = {(run["mapping"].get(h) or {}).get("field"): i for i, h in enumerate(headers) if (run["mapping"].get(h) or {}).get("field")}

    def g(r, f):
        i = fmap.get(f)
        return r[i].strip() if i is not None and i < len(r) and r[i] else None

    upload_id = run["upload_id"]
    entity = run["entity"]
    stats = {"sales": 0, "lines": 0, "customers": 0, "products_created": 0, "products_updated": 0,
             "products_no_cost": 0}
    # لو الملف ما فيه عمود تكلفة، لا نرمي الصفوف: ننشئ الصنف بتكلفة 0
    # ونعدّها، وننبّه إن الربح ما بينحسب إلا بعد ما تُدخل التكاليف.
    has_cost_col = "cost" in fmap
    # الفروع اللي أنشأها الاستيراد تلقائياً (اسم الفرع ظهر بالملف وما كان موجود).
    branches_created: list[str] = []
    # المرتجعات (كمية سالبة) لا تُستورد: قيمتها سالبة وتقلب الإيراد والربح،
    # والمحل يحتاج يشوفها بحسابه على حدة. نعدّها ونبلّغ عنها بصراحة.
    returns = {"lines": 0, "invoices": 0, "value": Decimal("0")}
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
        # Keyed by place, so "فرع خلدا" in this file finds the existing "Khalda" branch
        # instead of creating a second one (cleaning/arabic.py: place_key).
        branches: dict[str, str] = {}
        for b in await c.fetch("select id,name,name_ar from branches where org_id=$1 order by created_at", ctx.org_id):
            for nm in (b["name"], b["name_ar"]):
                if nm:
                    branches.setdefault(place_key(nm), b["id"])
        emps = {match_key(e["full_name"]): e["id"] for e in await c.fetch("select id, full_name from employees where org_id=$1", ctx.org_id)}
        product_rows = [dict(p) for p in await c.fetch("select id,name,cost,price,barcode,sku,category_id from products where org_id=$1", ctx.org_id)]
        names: dict[str, list[dict]] = defaultdict(list)
        barcodes: dict[str, list[dict]] = defaultdict(list)
        for product in product_rows:
            names[match_key(product["name"])].append(product)
            if product["barcode"] and _valid_barcode(product["barcode"]):
                barcodes[re.sub(r"\D", "", product["barcode"])].append(product)
        custs = {cu["phone"]: cu["id"] for cu in await c.fetch("select id, phone from customers where org_id=$1 and phone is not null", ctx.org_id)}
        cats: dict[str, str] = {match_key(r["name"]): r["id"] for r in await c.fetch("select id,name from categories where org_id=$1", ctx.org_id)}
        alias_done: set[tuple[str, str]] = set()
        employees_created: list[str] = []
        categories_created: list[str] = []

        emp_branch_done: set[str] = set()

        async def employee_id(name: str, branch: str | None = None):
            """يرجّع معرّف الموظف، وينشئه لو ظهر بالملف وما كان مسجَّل.

            الكاشير اسمه جوّا كل فاتورة. لو ما كان مسجَّلاً، كان يضيع
            واسمه ما بينربط بأي مبيعات — صفحة الموظفين تبقى فاضية
            رغم إن الملف فيه أسماء. ننشئه بوظيفة "cashier" وبدون راتب،
            وصفحة الموظفين بتخلّي المالك يكمّل بياناته بعدين.
            """
            if not name:
                return None
            k = match_key(name)
            if k in emps:
                eid = emps[k]
                # موظف موجود بلا فرع: نربطه بأول فرع يظهر معه.
                if branch and eid not in emp_branch_done:
                    emp_branch_done.add(eid)
                    await c.execute(
                        "update employees set branch_id=$2 where id=$1 and branch_id is null",
                        eid, branch)
                return eid
            eid = await c.fetchval(
                "insert into employees(org_id,branch_id,full_name,full_name_ar,job_title)"
                " values($1,$2,$3,$3,'cashier') returning id",
                ctx.org_id, branch, name)
            emps[k] = eid
            emp_branch_done.add(eid)
            employees_created.append(name)
            return eid

        async def category_id(name: str):
            """يرجّع معرّف الفئة، وينشئها لو ما كانت موجودة.

            عمود "الفئة" بملفات المبيعات كان يتجاهَل، فصفحة الأصناف
            تظهر كل شي بلا تصنيف و"أعلى فئة" بالداشبورد يبقى فاضي.
            """
            if not name:
                return None
            k = match_key(name)
            if k in cats:
                return cats[k]
            cid = await c.fetchval(
                "insert into categories(org_id,name,name_ar) values($1,$2,$2) returning id", ctx.org_id, name)
            cats[k] = cid
            categories_created.append(name)
            return cid

        async def branch_id(name: str):
            """يرجّع معرّف الفرع، وينشئه لو ظهر بالملف وما كان معرَّف.

            الرفض بـ "فرع غير معروف" كان يوقف الملف كامل. محل جديد ما
            عنده فروع مسجّلة بعد، أو فرع جديد فتح للتوّ — كلاهما وارد.
            الإنشاء هنا يحفظ الاسم كما ورد في الملف، والتنظيف يوحّد
            الأشكال المختلفة قبل الوصول لهنا.
            """
            k = place_key(name)
            if k in branches:
                return branches[k]
            bid = await c.fetchval(
                "insert into branches(org_id,name) values($1,$2) returning id", ctx.org_id, name)
            branches[k] = bid
            branches_created.append(name)
            return bid

        def find_product(name, barcode=None):
            if barcode and _valid_barcode(barcode):
                matches = barcodes.get(re.sub(r"\D", "", barcode), [])
                return matches[0] if len(matches) == 1 else None
            matches = names.get(match_key(name), [])
            return matches[0] if len(matches) == 1 else None

        async def product_id(name, price, cost=None, barcode=None, sku=None, category=None):
            k = match_key(name)
            existing = find_product(name, barcode)
            if existing:
                # هذان التعديلان يُنفَّذان مرة واحدة لكل صنف، مش لكل سطر.
                pid_e = existing["id"]
                if k != match_key(existing["name"]) and (pid_e, name) not in alias_done:
                    alias_done.add((pid_e, name))
                    await c.execute("""insert into product_aliases(org_id,product_id,alias,source)
                                       select $1,$2,$3,'import' where not exists
                                       (select 1 from product_aliases where org_id=$1 and product_id=$2 and alias=$3)""",
                                    ctx.org_id, pid_e, name)
                if category and not existing.get("category_id"):
                    cid = await category_id(category)
                    if cid:
                        await c.execute(
                            "update products set category_id=$2 where id=$1 and org_id=$3 and category_id is null",
                            pid_e, cid, ctx.org_id)
                        existing["category_id"] = cid
                return pid_e, existing["cost"]
            if cost is None:
                if not has_cost_col:
                    # الملف كله بلا تكلفة — ننشئ الصنف ونكمل، والتنبيه
                    # يطلع بالملخّص بدل ما نضيّع كل المبيعات.
                    stored_barcode0 = re.sub(r"\D", "", barcode) if barcode and _valid_barcode(barcode) else None
                    cid0 = await category_id(category) if category else None
                    pid0 = await c.fetchval(
                        "insert into products(org_id,name,sku,barcode,price,cost,upload_id,category_id)"
                        " values($1,$2,$3,$4,$5,0,$6,$7) returning id",
                        ctx.org_id, name, sku, stored_barcode0, price or 0, upload_id, cid0)
                    product = {"id": pid0, "name": name, "cost": 0, "price": price,
                               "barcode": stored_barcode0, "sku": sku, "category_id": cid0}
                    names[k].append(product)
                    if stored_barcode0:
                        barcodes[stored_barcode0].append(product)
                    stats["products_created"] += 1
                    stats["products_no_cost"] += 1
                    return pid0, 0
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
            cid = await category_id(category) if category else None
            pid = await c.fetchval("""insert into products(org_id,name,sku,barcode,price,cost,upload_id,category_id) values($1,$2,$3,$4,$5,$6,$7,$8) returning id""",
                                   ctx.org_id, name, sku, stored_barcode, price or 0, cost, upload_id, cid)
            product = {"id": pid, "name": name, "cost": cost, "price": price, "barcode": stored_barcode, "sku": sku, "category_id": cid}
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
                # لو أي سطر بالفاتورة عليه علم مالي (تاريخ مستقبلي/إجمالي
                # ناقص...) نتخطّى الفاتورة كاملة مع السبب، بدل ما توقف
                # الملف. فاتورة نصفها مشكوك فيه ما بتنستورد نصّها.
                hit = next((blocked_reasons[row_map[ri]] for ri, _r in lines
                            if ri < len(row_map) and row_map[ri] in blocked_reasons), None)
                if hit:
                    _skip(row_map[ri0], r0, hit[0], hit[1])
                    continue
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
                    # عمود وقت منفصل (Night/Afternoon/14:30) يُدمج مع التاريخ،
                    # وإلا ضاع وقت البيع وما بنقدر نحكي عن أوقات الذروة.
                    tm = g(r0, "sale_time")
                    if tm and ":" in tm:
                        try:
                            hh, mm = (int(x) for x in tm.split(":")[:2])
                            if 0 <= hh <= 23 and 0 <= mm <= 59:
                                sold = sold.replace(hour=hh, minute=mm)
                        except (ValueError, TypeError):
                            pass
                    branch_name = g(r0, "branch")
                    br = await branch_id(branch_name) if branch_name else None
                    emp = await employee_id(g(r0, "cashier"), br)
                    cust = custs.get(g(r0, "phone") or "")
                    items, subtotal = [], Decimal("0")
                    disc_lines, has_pct, saw_negative = Decimal("0"), False, False
                    for _ri, r in lines:
                        name = g(r, "product")
                        q = _num(g(r, "quantity"))
                        p = _num(g(r, "unit_price"))
                        t = _num(g(r, "total"))
                        cost = _num(g(r, "cost"))
                        if not name or q is None or q <= 0 or q > 200:
                            if q is not None and q < 0:
                                saw_negative = True
                                returns["lines"] += 1
                                returns["value"] += abs(_money(g(r, "total")) or Decimal("0"))
                            continue
                        if p is None and t is not None:
                            p = t / q
                        if p is None:
                            continue
                        price = _money(p)
                        if price is None:
                            raise SkippedRow(f"Invoice {inv}: invalid unit price {p}",
                                             f"الفاتورة {inv}: سعر وحدة غير صالح {p}", ri0)
                        pid, cost = await product_id(name, price, cost, g(r, "barcode"), g(r, "sku"), g(r, "category"))
                        lt = (Decimal(str(q)) * price).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                        # الخصم بالملفات قد يكون نسبة ("30%") أو مبلغاً (0.500).
                        d_raw = g(r, "discount")
                        d_amt = Decimal("0")
                        if d_raw:
                            if "%" in d_raw:
                                has_pct = True
                                try:
                                    pct = Decimal(re.sub(r"[^0-9.\-]", "", d_raw) or "0")
                                    d_amt = (lt * pct / Decimal("100")).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                                except (InvalidOperation, ValueError):
                                    d_amt = Decimal("0")
                            else:
                                d_amt = _money(d_raw) or Decimal("0")
                        disc_lines += d_amt
                        subtotal += lt
                        items.append((pid, Decimal(str(q)), price, cost, lt, d_amt))
                    if not items:
                        if saw_negative:
                            returns["invoices"] += 1
                        continue
                    sid = uuid.uuid4()
                    pm = g(r0, "payment_method")
                    if pm not in ("cash", "card", "cliq", "wallet", "online"):
                        raise SkippedRow(f"Invoice {inv}: unknown or missing payment method ({pm or 'empty'})",
                                         f"الفاتورة {inv}: طريقة دفع غير معروفة أو مفقودة ({pm or 'فارغ'})", ri0)
                    contract = run["batch_contract"] or {}
                    # لو الملف يحمل نسباً، مجموع خصومات البنود هو خصم الفاتورة.
                    discount = disc_lines if has_pct else (_money(g(r0, "discount") or 0) or Decimal("0"))
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
                    item_recs.extend((uuid.uuid4(), uuid.UUID(str(ctx.org_id)), sid, pid, q, p, cost, d_amt, lt) for pid, q, p, cost, lt, d_amt in items)
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
            old_costs, old_prices = [], []
            main_branch: list = []  # cached on first use

            async def save_stock(r, pid):
                """A product list's stock, reorder level and expiry (menu / inventory exports).

                These columns were mapped but never written, so every product showed 0 in stock.
                """
                reorder = _num(g(r, "minimum_stock"))
                if reorder is not None and 0 <= reorder < 1_000_000:
                    await c.execute("update products set reorder_level=$2 where id=$1 and org_id=$3",
                                    pid, int(round(reorder)), ctx.org_id)
                qty = _num(g(r, "stock"))
                if qty is None or qty < 0:
                    return
                bname = g(r, "branch")
                if bname:
                    bid = await branch_id(bname)
                else:
                    if not main_branch:
                        main_branch.append(await c.fetchval(
                            "select id from branches where org_id=$1 order by created_at limit 1", ctx.org_id))
                    bid = main_branch[0]
                if not bid:
                    return
                await c.execute("""insert into inventory_levels(org_id,branch_id,product_id,quantity) values($1,$2,$3,$4)
                                   on conflict (branch_id,product_id) do update set quantity=excluded.quantity, updated_at=now()""",
                                ctx.org_id, bid, pid, qty)
                stats["stock_levels"] = stats.get("stock_levels", 0) + 1
                exp = g(r, "expiry_date")
                if exp and qty > 0:
                    try:
                        day = dt.date.fromisoformat(exp[:10])
                    except ValueError:
                        return
                    await c.execute("delete from inventory_batches where org_id=$1 and branch_id=$2 and product_id=$3 and expiry_date=$4",
                                    ctx.org_id, bid, pid, day)
                    await c.execute("""insert into inventory_batches(org_id,branch_id,product_id,quantity,expiry_date,received_at)
                                       values($1,$2,$3,$4,$5,current_date)""", ctx.org_id, bid, pid, qty, day)

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
                    pid = existing["id"]
                    if cost:
                        old_costs.append((str(pid), float(existing["cost"])))
                        await c.execute("update products set cost=$2 where id=$1", pid, cost)
                        stats["products_updated"] += 1
                    # A product list (menu, catalog) is where selling prices come from: a
                    # price saved wrong by an earlier file (fils as dinars) gets corrected.
                    if entity == "products" and price and abs(price - float(existing["price"] or 0)) > 0.0005:
                        old_prices.append((str(pid), float(existing["price"] or 0)))
                        await c.execute("update products set price=$2 where id=$1", pid, price)
                        existing["price"] = price
                else:
                    try:
                        pid, _ = await product_id(name, price or 0, cost, g(r, "barcode"), g(r, "sku"))
                    except SkippedRow as exc:
                        _skip(ri, r, exc.reason, exc.reason_ar)
                        continue
                if entity == "products":
                    await save_stock(r, pid)
            stats["old_costs"] = old_costs
            stats["old_prices"] = old_prices
        learned = 0
        # Only merges the user approved become memory. Learning every merge that
        # wasn't rejected saved Idrak's own unreviewed guesses (a garlic sack →
        # "Mixed Grill 1kg") as rules that then rewrote every later file.
        pairs = {(ch["column_name"], ch["old_value"], ch["new_value"]) for ch in changes if ch["rule"] in MERGE_RULES and ch["status"] == "approved"}
        rule_recs = []
        for col, old, new in list(pairs)[:150]:
            kind = kind_of((run["mapping"].get(col) or {}).get("field"))
            if kind and old and new and match_key(old) != match_key(new):
                rule_recs.append((ctx.org_id, kind, old, new, ctx.user.id))
                learned += 1
        if rule_recs:
            await c.executemany("""insert into cleaning_rules(org_id,column_kind,match_value,replace_value,created_by) values($1,$2,$3,$4,$5)
                                   on conflict (org_id,column_kind,match_value) do update set times_applied = cleaning_rules.times_applied + 1""", rule_recs)
        # Memory rules that rewrote values in this file: +1 each (the data page's
        # "applied" counter, which only moved when a rule was re-learned).
        hit = {(kind_of((run["mapping"].get(ch["column_name"]) or {}).get("field")), match_key(ch["old_value"]))
               for ch in changes if ch["rule"] == "memory" and ch["status"] != "rejected" and ch["old_value"]}
        if hit:
            rule_ids = {(KIND_ALIAS.get(rr["column_kind"], rr["column_kind"]), match_key(rr["match_value"])): rr["id"]
                        for rr in await c.fetch("select id, column_kind, match_value from cleaning_rules"
                                                " where org_id=$1 and column_kind<>'column'", ctx.org_id)}
            bumps = [(rule_ids[k],) for k in hit if k in rule_ids]
            if bumps:
                await c.executemany("update cleaning_rules set times_applied = times_applied + 1 where id=$1", bumps)
        await c.execute("update cleaning_changes set status='approved' where run_id=$1 and status='proposed'", run_id)
        imported = stats["sales"] or stats["customers"] or (stats["products_created"] + stats["products_updated"])
        # نُخزّن الصفوف المتخطّاة في stats حتى يقدر المستخدم ينزّلها كـ CSV.
        # قد تكون كبيرة، فنقصّها على 500 سبب مع عدّاد كلّي.
        skipped_blob = {"count": len(skipped), "items": skipped[:500]}
        await c.execute("update cleaning_runs set status='imported', imported_at=now(), reverted_at=null, stats = stats || $2 where id=$1",
                        run_id, {"import": {k: v for k, v in stats.items() if k not in ("old_costs", "old_prices")}, "learned_rules": learned, "old_costs": stats.get("old_costs", []), "old_prices": stats.get("old_prices", []),
                                 "skipped": skipped_blob, "branches_created": branches_created,
                                 "employees_created": employees_created, "categories_created": categories_created,
                                 "returns": {"lines": returns["lines"], "invoices": returns["invoices"],
                                             "value": float(returns["value"])}})
        await c.execute("update uploads set status='imported', imported_rows=$2 where id=$1", upload_id, imported)
    db.cache_clear()
    await db.audit(ctx.org_id, ctx.user.id, "cleaning.applied", "upload", str(upload_id), {"file": run["file_name"], "skipped": len(skipped),
                                                                                           **{k: v for k, v in stats.items() if k not in ("old_costs", "old_prices")}})
    await db.execute("insert into notifications(org_id,kind,title,link) values($1,'cleaning',$2,$3)", ctx.org_id,
                     f"{run['file_name']} cleaned & imported: {run['score_before']['score']:.0f} → {run['score_after']['score']:.0f}", f"/app/data/runs/{run_id}")
    return {"ok": True, "imported": {k: v for k, v in stats.items() if k not in ("old_costs", "old_prices")}, "learned_rules": learned,
            "skipped": {"count": len(skipped), "sample": skipped[:20]},
            "branches_created": branches_created,
            "employees_created": employees_created,
            "categories_created": categories_created,
            "returns": {"lines": returns["lines"], "invoices": returns["invoices"],
                        "value": float(returns["value"])}}


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
        for pid, price in (run["stats"] or {}).get("old_prices", []):
            await c.execute("update products set price=$2 where id=$1 and org_id=$3", pid, price, ctx.org_id)
        await c.execute("delete from products p where p.upload_id=$1 and p.org_id=$2 and not exists (select 1 from sale_items si where si.product_id=p.id)", run["upload_id"], ctx.org_id)
        await c.execute("update cleaning_runs set status='reverted', reverted_at=now() where id=$1", run_id)
        await c.execute("update uploads set status='cleaned', imported_rows=0 where id=$1", run["upload_id"])
    db.cache_clear()
    await db.audit(ctx.org_id, ctx.user.id, "cleaning.undone", "upload", str(run["upload_id"]))
    return {"ok": True, "sales_removed": int(n1.split()[-1]), "customers_removed": int(n2.split()[-1])}


@router.post("/clear-all")
async def clear_all_data(ctx: Ctx = Depends(require("upload_data"))):
    """يمسح كل بيانات التشغيل للمؤسسة ويرجّعها لصفحة بيضاء.

    بعد تجارب رفع كثيرة تبقى أصناف وفروع وموظفون من ملفات قديمة، والأرقام
    ما عادت مفهومة. هذا يمسح المبيعات والزبائن والأصناف والموظفين والفروع
    والفئات والملفات — ويترك الحساب والفريق والإعدادات.
    """
    async with db.transaction() as c:
        n_sales = await c.execute("delete from sales where org_id=$1", ctx.org_id)
        n_cust = await c.execute("delete from customers where org_id=$1", ctx.org_id)
        n_prod = await c.execute("delete from products where org_id=$1", ctx.org_id)
        n_emp = await c.execute("delete from employees where org_id=$1", ctx.org_id)
        n_goals = await c.execute("delete from goals where org_id=$1", ctx.org_id)
        # الفروع: نُبقي فرعاً واحداً حتى تظل الواجهة صالحة للاستخدام،
        # ونعيد تسميته للاسم الافتراضي.
        keep = await c.fetchval("select id from branches where org_id=$1 order by created_at limit 1", ctx.org_id)
        if keep:
            await c.execute("delete from branches where org_id=$1 and id<>$2", ctx.org_id, keep)
            await c.execute("update branches set name='Main branch', name_ar='الفرع الرئيسي' where id=$1", keep)
        n_cat = await c.execute("delete from categories where org_id=$1", ctx.org_id)
        n_up = await c.execute("delete from uploads where org_id=$1", ctx.org_id)
        await c.execute("delete from import_batches where org_id=$1", ctx.org_id)
        await c.execute("delete from notifications where org_id=$1", ctx.org_id)
    db.cache_clear()
    counts = {"sales": _rowcount(n_sales), "customers": _rowcount(n_cust), "products": _rowcount(n_prod),
              "employees": _rowcount(n_emp), "goals": _rowcount(n_goals), "categories": _rowcount(n_cat),
              "uploads": _rowcount(n_up)}
    await db.audit(ctx.org_id, ctx.user.id, "org.cleared", "organization", ctx.org_id, counts)
    return {"ok": True, "deleted": counts}


@router.delete("/uploads/{upload_id}")
async def delete_upload(upload_id: str, ctx: Ctx = Depends(require("upload_data"))):
    """حذف نهائي لملفّ مرفوع وكل ما نتج عنه.

    تحذير: هذا الحذف لا يُتراجع عنه. يحذف:
    - الـ upload وسجلّ التنظيف وكل التغييرات
    - المبيعات/الزبائن/الأصناف الناتجة عنه (upload_id = هذا الملف)
    - الأصناف التي أنشأها هذا الملف ولم تُستخدم في أي مبيعات أخرى

    لا يحذف القواعد المتعلَّمة في cleaning_rules — تلك تخصّ المؤسسة
    كلّها، ولا صلة لها بملفّ واحد.
    """
    exists = await db.fetchrow("select id, batch_id, columns, mapping from uploads where id=$1 and org_id=$2", upload_id, ctx.org_id)
    if not exists:
        raise HTTPException(404, "Upload not found")
    batch_id = exists["batch_id"]
    # نقرأ أسماء الفروع/الموظفين/الفئات اللي أنشأها هذا الاستيراد قبل ما
    # ينحذف سجلّ التنظيف (بينحذف مع الملف). بدونها كانت تبقى معلّقة
    # بصفحات الفروع والموظفين والأصناف بعد حذف الملف.
    run_stats = await db.fetchval(
        "select stats from cleaning_runs where upload_id=$1 and org_id=$2 order by started_at desc limit 1",
        upload_id, ctx.org_id) or {}
    made_branches = [b for b in (run_stats.get("branches_created") or []) if b]
    made_emps = [e for e in (run_stats.get("employees_created") or []) if e]
    made_cats = [c for c in (run_stats.get("categories_created") or []) if c]
    # ملفات قديمة (رُفعت قبل ما نسجّل هذه الأسماء): نستخرجها من بيانات
    # الملف نفسه. بدونها تبقى فروع وموظفون معلّقون للأبد بعد الحذف.
    if not (made_branches and made_emps):
        raw = await db.fetchval("select raw_rows from upload_data where upload_id=$1", upload_id)
        cols = exists["columns"] or []
        m = exists["mapping"] or {}
        idx = {field: i for i, h in enumerate(cols) if (field := (m.get(h) or {}).get("field"))}
        def _names(field):
            i = idx.get(field)
            if i is None or not raw:
                return []
            return sorted({str(r[i]).strip() for r in raw
                           if i < len(r) and r[i] not in (None, "")})
        if not made_branches:
            made_branches = _names("branch")
        if not made_emps:
            made_emps = _names("cashier")
        if not made_cats:
            made_cats = _names("category")
    async with db.transaction() as c:
        sales_n = await c.execute("delete from sales where upload_id=$1 and org_id=$2", upload_id, ctx.org_id)
        cust_n = await c.execute("delete from customers where upload_id=$1 and org_id=$2", upload_id, ctx.org_id)
        # الأصناف اللي أنشأها هذا الملف فقط، وبدون استخدام في مبيعات أخرى.
        prod_n = await c.execute(
            """delete from products p
               where p.upload_id=$1 and p.org_id=$2
                 and not exists (select 1 from sale_items si where si.product_id=p.id)
                 and not exists (select 1 from purchase_items pi where pi.product_id=p.id)""",
            upload_id, ctx.org_id)
        # الفروع/الموظفون/الفئات التي وُلدت من هذا الملف، وبقيت بلا أي
        # ارتباط — تنحذف معه. أي واحدة عندها مبيعات أو أهداف تبقى.
        br_n = emp_n = cat_n = "DELETE 0"
        if made_branches:
            br_n = await c.execute(
                """delete from branches b where b.org_id=$1 and b.name = any($2::text[])
                     and not exists (select 1 from sales s where s.branch_id=b.id)
                     and not exists (select 1 from employees e where e.branch_id=b.id)
                     and not exists (select 1 from goals g where g.branch_id=b.id)""",
                ctx.org_id, made_branches)
        if made_emps:
            emp_n = await c.execute(
                """delete from employees e where e.org_id=$1 and e.full_name = any($2::text[])
                     and not exists (select 1 from sales s where s.employee_id=e.id)""",
                ctx.org_id, made_emps)
        if made_cats:
            cat_n = await c.execute(
                """delete from categories cc where cc.org_id=$1 and cc.name = any($2::text[])
                     and not exists (select 1 from products p where p.category_id=cc.id)""",
                ctx.org_id, made_cats)
        # upload_data / cleaning_runs / cleaning_changes تُحذف بـ cascade.
        await c.execute("delete from uploads where id=$1 and org_id=$2", upload_id, ctx.org_id)
        # لو الدفعة صارت فاضية، نشيلها كمان حتى ما تظل صفوف يتيمة.
        if batch_id:
            left = await c.fetchval("select count(*) from uploads where batch_id=$1 and org_id=$2", batch_id, ctx.org_id)
            if not left:
                await c.execute("delete from import_batches where id=$1 and org_id=$2", batch_id, ctx.org_id)
    db.cache_clear()
    counts = {"sales": _rowcount(sales_n), "customers": _rowcount(cust_n), "products": _rowcount(prod_n),
              "branches": _rowcount(br_n), "employees": _rowcount(emp_n), "categories": _rowcount(cat_n)}
    await db.audit(ctx.org_id, ctx.user.id, "upload.deleted", "upload", upload_id, counts)
    return {"ok": True, "deleted": counts}


@router.delete("/batches/{batch_id}")
async def delete_batch(batch_id: str, ctx: Ctx = Depends(require("upload_data"))):
    """حذف نهائي لدفعة كاملة وكل ملفاتها وكل ما نتج عنها."""
    b = await db.fetchrow("select id from import_batches where id=$1 and org_id=$2", batch_id, ctx.org_id)
    if not b:
        raise HTTPException(404, "Batch not found")
    ids = [str(r["id"]) for r in await db.fetch("select id from uploads where batch_id=$1 and org_id=$2", batch_id, ctx.org_id)]
    totals = {"sales": 0, "customers": 0, "products": 0, "files": 0}
    for uid in ids:
        async with db.transaction() as c:
            s = await c.execute("delete from sales where upload_id=$1 and org_id=$2", uid, ctx.org_id)
            cu = await c.execute("delete from customers where upload_id=$1 and org_id=$2", uid, ctx.org_id)
            p = await c.execute(
                """delete from products p
                   where p.upload_id=$1 and p.org_id=$2
                     and not exists (select 1 from sale_items si where si.product_id=p.id)
                     and not exists (select 1 from purchase_items pi where pi.product_id=p.id)""",
                uid, ctx.org_id)
            await c.execute("delete from uploads where id=$1 and org_id=$2", uid, ctx.org_id)
        totals["sales"] += _rowcount(s)
        totals["customers"] += _rowcount(cu)
        totals["products"] += _rowcount(p)
        totals["files"] += 1
    async with db.transaction() as c:
        await c.execute("delete from import_batches where id=$1 and org_id=$2", batch_id, ctx.org_id)
    db.cache_clear()
    await db.audit(ctx.org_id, ctx.user.id, "batch.deleted", "batch", batch_id, totals)
    return {"ok": True, "deleted": totals}


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
    # ترويسات HTTP تُرمّز latin-1، واسم الملف عربي فينهار الطلب (كان هذا
    # سبب "network" عند تنزيل المتخطّاة). الحل: نسخة ASCII للأنظمة القديمة
    # + filename* بترميز UTF-8 حسب RFC 5987.
    ascii_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", fn).strip("_") or "import"
    from urllib.parse import quote
    disposition = (f'attachment; filename="skipped_{ascii_name}.csv"; '
                   f"filename*=UTF-8''{quote('skipped_' + fn + '.csv')}")
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"content-disposition": disposition})


@router.get("/rules")
async def rules(ctx: Ctx = Depends(require("view_dashboard"))):
    return await db.fetch("""select r.*, p.full_name created_by_name from cleaning_rules r left join profiles p on p.id=r.created_by
                             where r.org_id=$1 order by r.times_applied desc, r.created_at desc""", ctx.org_id)


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, ctx: Ctx = Depends(require("clean_data"))):
    await db.execute("delete from cleaning_rules where id=$1 and org_id=$2", rule_id, ctx.org_id)
    return {"ok": True}

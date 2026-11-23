from rapidfuzz import fuzz, process

from .arabic import match_key

FIELDS: dict[str, tuple[str, list[str]]] = {
    "invoice_number": ("id", ["invoice", "invoice no", "invoice number", "inv", "inv no", "receipt", "receipt no", "bill no", "رقم الفاتورة", "فاتورة", "الفاتورة", "رقم الايصال", "transaction id",
                                 # أنظمة المطاعم تسمّي الفاتورة "طلب".
                                 "رقم الطلب", "رقم الطلبية", "رقم الاوردر", "order no", "order number", "order id"]),
    "date": ("date", ["date", "day", "sold at", "datetime", "sale date", "transaction date", "تاريخ", "التاريخ", "تاريخ البيع", "time", "الوقت"]),
    # عمود وقت منفصل عن التاريخ (Night / Afternoon / 14:30). إدراك يخزّن
    # البيع بتاريخ ووقت مع بعض، فنقرأ العمودين وندمجهم وقت الاستيراد.
    "sale_time": ("time", ["time of sale", "sale time", "time of day", "hour", "shift", "وقت البيع", "وقت العمليه", "الساعة",
                         "وقت الطلب", "order time"]),    "branch": ("branch", ["branch", "store", "shop", "location", "outlet", "فرع", "الفرع", "المحل", "الموقع"]),
    "cashier": ("person", ["cashier", "employee", "staff", "user", "sales person", "received by", "served by", "كاشير", "الكاشير", "الموظف", "موظف", "البائع"]),
    "product": ("product", ["product", "item", "item name", "product name", "description", "sku name", "اسم الصنف", "الصنف", "صنف", "المنتج", "اسم المنتج", "البند", "المادة"]),
    "barcode": ("barcode", ["barcode", "ean", "upc", "باركود", "الباركود"]),
    "sku": ("id", ["sku", "item code", "code", "رمز الصنف", "كود الصنف", "كود"]),
    "category": ("category", ["category", "department", "group", "item type", "product type", "item category", "الفئة", "التصنيف", "القسم"]),
    "quantity": ("quantity", ["qty", "quantity", "units", "count", "pcs", "الكمية", "كمية", "العدد", "عدد"]),
    "unit_price": ("money", ["price", "unit price", "selling price", "sale price", "item price", "unit amount", "سعر الوحدة", "السعر", "سعر", "سعر البيع", "سعر الحبة"]),
    "cost": ("money", ["cost", "unit cost", "purchase price", "التكلفة", "سعر الشراء", "الكلفة"]),
    "total": ("money", ["total", "amount", "line total", "net", "net amount", "value", "transaction amount", "grand total", "الإجمالي", "الاجمالي", "المجموع", "المبلغ", "القيمة"]),
    "discount": ("money", ["discount", "disc", "خصم", "الخصم"]),
    "tax": ("money", ["tax", "vat", "sales tax", "ضريبة", "الضريبة", "ضريبة المبيعات"]),
    "payment_method": ("payment", ["payment", "payment method", "pay method", "tender", "method", "transaction type", "payment type", "طريقة الدفع", "الدفع", "وسيلة الدفع"]),
    "customer_name": ("person", ["customer", "customer name", "client", "name", "full name", "الزبون", "اسم الزبون", "العميل", "اسم العميل", "الاسم"]),
    "phone": ("phone", ["phone", "mobile", "tel", "telephone", "whatsapp", "customer phone", "phone number", "موبايل", "رقم الموبايل", "هاتف", "الهاتف", "رقم الهاتف", "جوال", "واتس",
                        "هاتف الزبون", "رقم هاتف الزبون", "جوال الزبون", "موبايل الزبون", "هاتف العميل", "رقم هاتف العميل"]),
    "email": ("email", ["email", "e-mail", "mail", "البريد", "البريد الالكتروني", "ايميل", "الايميل", "الإيميل"]),
    "city": ("city", ["city", "town", "المدينة", "مدينة", "المحافظة"]),
    "area": ("area", ["area", "district", "neighborhood", "neighbourhood", "region", "المنطقة", "منطقة", "الحي"]),
    "supplier": ("company", ["supplier", "vendor", "distributor", "المورد", "مورد", "الموزع", "اسم المورد", "supplier name", "vendor name"]),
    "carton_price": ("money", ["carton price", "case price", "سعر الكرتونة", "سعر الكرتونه"]),
    "pack_size": ("quantity", ["pack size", "units per case", "case qty", "عدد الحبات بالكرتونة", "عدد الحبات بالكرتونه", "عدد بالكرتونة"]),
    "stock": ("quantity", ["stock", "on hand", "inventory", "balance", "المخزون", "الرصيد", "الكمية المتوفرة", "الكمية بالمخزون", "الكمية في المخزون"]),
    "minimum_stock": ("quantity", ["minimum stock", "min stock", "reorder level", "الحد الأدنى", "الحد الادنى", "حد الطلب"]),
    "expiry_date": ("date", ["expiry", "expiry date", "exp", "best before", "تاريخ الانتهاء", "الانتهاء", "تاريخ الصلاحية", "تاريخ انتهاء الصلاحية", "انتهاء الصلاحية"]),
    "updated_at": ("date", ["last updated", "updated", "update date", "تاريخ آخر تحديث", "تاريخ التحديث", "اخر تحديث"]),
    "notes": ("text", ["notes", "note", "comment", "comments", "remarks", "ملاحظات", "ملاحظة"]),
    "gender": ("gender", ["gender", "sex", "الجنس"]),
}

LABELS = {
    "invoice_number": ("Invoice number", "رقم الفاتورة"), "date": ("Date", "التاريخ"), "sale_time": ("Time of sale", "وقت البيع"), "branch": ("Branch", "الفرع"),
    "cashier": ("Cashier", "الكاشير"), "product": ("Product", "الصنف"), "barcode": ("Barcode", "الباركود"), "sku": ("SKU", "رمز الصنف"),
    "category": ("Category", "الفئة"), "quantity": ("Quantity", "الكمية"), "unit_price": ("Unit price", "سعر الوحدة"),
    "cost": ("Cost", "التكلفة"), "total": ("Total", "الإجمالي"), "discount": ("Discount", "الخصم"), "tax": ("Tax", "الضريبة"),
    "payment_method": ("Payment method", "طريقة الدفع"), "customer_name": ("Customer name", "اسم الزبون"), "phone": ("Phone", "الهاتف"),
    "email": ("Email", "الإيميل"), "city": ("City", "المدينة"), "area": ("Area", "المنطقة"), "supplier": ("Supplier", "المورد"),
    "carton_price": ("Carton price", "سعر الكرتونة"), "pack_size": ("Pack size", "عدد الحبات"), "stock": ("Stock", "المخزون"), "minimum_stock": ("Minimum stock", "الحد الأدنى"),
    "expiry_date": ("Expiry date", "تاريخ الانتهاء"), "updated_at": ("Last updated", "آخر تحديث"), "notes": ("Notes", "ملاحظات"),
    "gender": ("Gender", "الجنس"),
}

REQUIRED = {
    "sales": ["date", "product", "quantity", "unit_price"],
    "customers": ["customer_name", "phone"],
    "products": ["product", "unit_price"],
    "supplier_prices": ["supplier", "product", "unit_price"],
    "unknown": [],
}

ENTITY_LABELS = {
    "sales": ("Sales transactions", "حركات مبيعات"), "customers": ("Customer list", "قائمة زبائن"),
    "products": ("Product catalog", "قائمة أصناف"), "supplier_prices": ("Supplier price list", "قائمة أسعار مورد"),
    "unknown": ("Generic table", "جدول عام"),
}

_SYN = [(match_key(s), f) for f, (_, syns) in FIELDS.items() for s in syns + [f.replace("_", " ")]]
_SYN_KEYS = [k for k, _ in _SYN]
_EXACT: dict[str, str] = {}
for _key, _field in _SYN:
    _EXACT.setdefault(_key, _field)  # أول مرادف يفوز، نفس سلوك الحلقة القديمة


def header_key(header) -> str:
    """A header as the matcher reads it; also the key of the shared synonyms and file fingerprints."""
    # أسماء الأعمدة بالأنظمة كثير فيها شرطات سفلية (item_name، received_by).
    # match_key بتخلّي "_" لأنها حرف كلمة، فما كانت تطابق المرادفات
    # المكتوبة بمسافة. نبدّلها قبل التطبيع.
    return match_key(str(header or "").replace("_", " "))


def guess_field(header: str) -> tuple[str | None, float]:
    k = header_key(header)
    if not k:
        return None, 0.0
    if k in _EXACT:
        return _EXACT[k], 1.0
    # token_set_ratio يعطي 100 لأي مرادف كل كلماته داخل العنوان: "تاريخ" و
    # "تاريخ الانتهاء" يتعادلان على "تاريخ الانتهاء للصلاحية"، و"الاسم" و
    # "المورد" على "اسم المورد". كان يفوز أول مرادف بالقائمة، وهو العام.
    # الآن أعلى درجة، وعند التعادل الأطول (الأكثر تحديداً). والتقريبية تبقى
    # ≤ 0.99 حتى تغلبها التامة عند التنافس على نفس الحقل في auto_map.
    hits = process.extract(k, _SYN_KEYS, scorer=fuzz.token_set_ratio, limit=None, score_cutoff=86)
    if not hits:
        return None, 0.0
    top = max(score for _, score, _ in hits)
    _, score, idx = max((h for h in hits if h[1] == top), key=lambda h: (len(h[0]), -h[2]))
    return _SYN[idx][1], min(score, 99) / 100


# "الوقت" مرادف للتاريخ لأن بعض الأنظمة تضع التاريخ والوقت بعمود اسمه Time.
# لكن لما يكون فيه عمود تاريخ مستقل ("التاريخ" + "الوقت")، عمود الوقت هو وقت
# البيع، وكان يضيع لأن حقل التاريخ محجوز.
_TIME_WORDS = {match_key(w) for w in ("time", "الوقت", "الساعة", "hour")}


def _is_time_header(header: str) -> bool:
    return bool(set(match_key(str(header or "").replace("_", " ")).split()) & _TIME_WORDS)


# A shared synonym (a header >= 3 companies confirmed, cleaning/learning.py)
# is trusted like a good header match; the values still have the last word.
SHARED_CONF = 0.95


def auto_map(headers: list[str], rows: list[list] | None = None,
             shared: dict[str, str] | None = None) -> dict[str, dict]:
    """Map headers to fields. With rows, the values are checked too (see profile.py):
    each entry then also carries "review" and "evidence".

    shared: header_key -> field learned across companies (learning.promote). It
    beats a fuzzy match, never an exact built-in synonym; its columns get
    source "shared".
    """
    names = _map_by_name(headers, shared)
    if rows is None:
        return names
    from .profile import refine_with_values  # profile imports this module
    return refine_with_values(headers, rows, names)


def _guess(header: str, shared: dict[str, str] | None) -> tuple[str | None, float, str | None, int]:
    """(field, confidence, source, tier): tier 0 exact built-in, 1 shared, 2 fuzzy, 3 nothing."""
    f, conf = guess_field(header)
    if f and conf >= 1.0:
        return f, conf, "rules", 0
    if shared and (s := shared.get(header_key(header))) in FIELDS:
        return s, SHARED_CONF, "shared", 1
    return (f, conf, "rules", 2) if f else (None, 0.0, None, 3)


def _map_by_name(headers: list[str], shared: dict[str, str] | None = None) -> dict[str, dict]:
    guesses = {h: _guess(h, shared) for h in headers}
    # نوزّع الحقول بالأقوى أولاً (التامّة، ثم المرادف المشترك، ثم التقريبية)
    # حتى لا يحجز عمود تقريبي ("حالة الدفع") حقلاً يطابقه عمود آخر تماماً
    # ("طريقة الدفع"). عند التعادل: أعمدة الوقت بعد غيرها (فيأخذ "التاريخ"
    # حقل التاريخ)، ثم ترتيب الأعمدة الأصلي.
    order = sorted(range(len(headers)),
                   key=lambda i: (guesses[headers[i]][3], -guesses[headers[i]][1], _is_time_header(headers[i]), i))
    used: set[str] = set()
    chosen: dict[str, tuple[str | None, float, str | None]] = {}
    for i in order:
        h = headers[i]
        f, conf, source, _ = guesses[h]
        if f == "date" and "date" in used and "sale_time" not in used and _is_time_header(h):
            f = "sale_time"
        if f and f in used:
            f, conf = None, 0.0
        if f:
            used.add(f)
        chosen[h] = (f, conf, source if f else None)
    return {h: {"field": chosen[h][0], "confidence": round(chosen[h][1], 2), "source": chosen[h][2]} for h in headers}


_WASTE_PREFIXES = tuple(match_key(w) for w in ("هدر", "تالف", "waste", "spoil"))
_PURCHASE_PREFIXES = tuple(match_key(w) for w in ("مورد", "مشتريات", "supplier", "vendor", "purchas"))
_PURCHASE_WORDS = {match_key(w) for w in ("شراء", "الشراء", "purchase", "purchases")}


def _header_tokens(headers: list[str] | None) -> set[str]:
    return {t for h in headers or () for t in match_key(str(h or "").replace("_", " ")).split()}


def _starts_with_any(tokens: set[str], prefixes: tuple[str, ...]) -> bool:
    return any(t.startswith(p) for t in tokens for p in prefixes)


def _looks_purchase(fields: set[str], tokens: set[str]) -> bool:
    return "supplier" in fields or _starts_with_any(tokens, _PURCHASE_PREFIXES) or bool(tokens & _PURCHASE_WORDS)


def detect_entity(fields: set[str], headers: list[str] | None = None) -> str:
    return _detect(fields, _header_tokens(headers))[0]


def _detect(fields: set[str], tokens: set[str], guards: bool = True) -> tuple[str, str | None]:
    """(entity, the guard that decided it: "waste" | "purchase" | None)."""
    if guards:
        # سجلّ هدر/تالف (صنف + كمية + تاريخ) كان يُقرأ مبيعات، فيدخل الهدر كإيراد.
        # إدراك ما بيدعم الهدر لسا، فالأسلم جدول عام لا يُستورد منه شيء.
        if _starts_with_any(tokens, _WASTE_PREFIXES) and not ({"cashier", "customer_name", "payment_method"} & fields):
            return "unknown", "waste"
        # فواتير مشتريات من مورد كانت تُقرأ مبيعات (واسم المورد كزبون) فتتسجّل
        # المشتريات كإيرادات. نعاملها كقائمة أسعار مورد: تحدّث تكلفة الأصناف فقط.
        # لا ينطبق على مبيعات فيها كاشير/زبون، ولا على كتالوج أصناف فيه مخزون.
        if _looks_purchase(fields, tokens) and not ({"cashier", "customer_name", "stock", "minimum_stock"} & fields):
            if "product" in fields and ({"unit_price", "cost", "carton_price"} & fields):
                return "supplier_prices", "purchase"
            return "unknown", "purchase"
    return _detect_by_fields(fields), None


def _detect_by_fields(fields: set[str]) -> str:
    if {"product", "quantity"} <= fields and ({"date", "invoice_number"} & fields):
        return "sales"
    # Stock first: a menu or inventory list names a default supplier and a unit of
    # measure too, and read as supplier prices it lost its selling prices and stock.
    if "product" in fields and ({"stock", "minimum_stock"} & fields):
        return "products"
    if "supplier" in fields and ({"carton_price", "pack_size"} & fields):
        return "supplier_prices"
    if "supplier" in fields and "cost" in fields and "stock" not in fields:
        return "supplier_prices"
    if "product" in fields and ({"unit_price", "cost", "stock", "barcode"} & fields):
        return "products"
    if {"customer_name", "phone"} & fields:
        return "customers"
    return "unknown"


# ── Is the detected file type safe to import without asking? ──────────────────
# detect_entity() always answers, even when its signals are weak or point two
# ways. A wrong type is the costliest mistake (purchases imported as revenue, a
# waste log as sales), so the mapping screen asks the user to confirm the type
# whenever one of these holds, and clean/apply refuse until they have:
#   purchase_guard / waste_guard  a guard turned what the fields alone read as
#                                 another type into supplier_prices / unknown
#   mixed_signals                 read as sales, but the headers also talk about
#                                 suppliers, purchases or waste
#   missing_required              the type's import needs a field no column has
#   unconfirmed_fields            the type changes if the columns still under
#                                 review (or filled by the AI alone) are left out
#   unrecognized                  nothing tells what the file is (generic table)

ENTITIES = tuple(REQUIRED)

# What importing each type really needs; each item is met by any of its fields.
# The importer derives a sale's unit price from total ÷ quantity, and a supplier
# price list stores the cost column, else the price.
_STANDS_IN = {("sales", "unit_price"): ["total"], ("supplier_prices", "unit_price"): ["cost"]}
NEEDS = {e: [[f, *_STANDS_IN.get((e, f), [])] for f in fs] for e, fs in REQUIRED.items()}

# The user's confirmed type is kept inside uploads.mapping under this key (no
# schema change). Every reader of mapping looks columns up by header, so a
# header with this exact name is the only clash, and set_mapping refuses it.
ENTITY_KEY = "__idrak_entity__"


def missing_for(entity: str, fields: set[str]) -> list[str]:
    return [item[0] for item in NEEDS.get(entity, []) if not set(item) & fields]


def _mapped(cols: dict[str, dict]) -> set[str]:
    return {m["field"] for m in cols.values() if m.get("field")}


def entity_check(headers: list[str], cols: dict[str, dict]) -> dict:
    """Detected type plus the reasons it needs the user's confirmation.

    cols: header -> mapping entry ({"field", "review", ...}), headers only.
    """
    fields = _mapped(cols)
    tokens = _header_tokens(headers)
    entity, guard = _detect(fields, tokens)
    reasons: list[dict] = []
    suggested: list[str] = []

    if guard:
        plain = _detect_by_fields(fields)
        if plain != entity:
            # Not suggested: the fields-only reading (usually sales) is the very
            # mistake the guard prevents. The user can still choose it.
            reasons.append({"code": f"{guard}_guard", "instead_of": plain})
    elif entity == "sales":
        signal = ("purchase" if _looks_purchase(fields, tokens)
                  else "waste" if _starts_with_any(tokens, _WASTE_PREFIXES) else None)
        if signal:
            reasons.append({"code": "mixed_signals", "signal": signal})
            suggested.append("supplier_prices" if signal == "purchase" else "unknown")
    if entity != "unknown" and (missing := missing_for(entity, fields)):
        reasons.append({"code": "missing_required", "fields": missing})
    # Under review, or filled by the AI alone (no header match): neither may
    # decide the type without the user seeing it.
    unsure = [h for h in headers if (m := cols.get(h) or {}).get("field")
              and (m.get("review") or m.get("source") == "ai")]
    if unsure:
        sure = _mapped({h: m for h, m in cols.items() if h not in unsure})
        without = _detect(sure, tokens)[0]
        if without != entity:
            reasons.append({"code": "unconfirmed_fields", "columns": unsure, "instead_of": without})
            suggested.append(without)
    if entity == "unknown" and not guard:
        reasons.append({"code": "unrecognized"})
    return {"detected": entity, "needs_confirmation": bool(reasons), "reasons": reasons,
            "suggested": [e for i, e in enumerate(suggested) if e != entity and e not in suggested[:i]]}


def field_signature(cols: dict[str, dict]) -> list[list[str]]:
    """Which column holds which field; a confirmation is only valid for this mapping."""
    return sorted([h, m["field"]] for h, m in cols.items() if m.get("field"))


def entity_state(headers: list[str], mapping: dict | None) -> dict:
    """entity_check() plus the user's saved confirmation, read from uploads.mapping.

    "entity" is the type to clean and import with (the confirmed one, else the
    detected one) and "blocked" means it may not be cleaned or imported yet.
    """
    mapping = mapping or {}
    cols = {h: mapping.get(h) or {} for h in headers}
    state = entity_check(headers, cols)
    saved = mapping.get(ENTITY_KEY) or {}
    ok = saved.get("entity") in ENTITIES and saved.get("fields") == field_signature(cols)
    state["confirmed"] = saved["entity"] if ok else None
    # "file": carried over from the company's last file with the same columns.
    state["confirmed_via"] = saved.get("via") if ok else None
    state["entity"] = state["confirmed"] or state["detected"]
    state["blocked"] = state["needs_confirmation"] and not state["confirmed"]
    return state


def kind_of(field: str | None) -> str | None:
    return FIELDS[field][0] if field in FIELDS else None

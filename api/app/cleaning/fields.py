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


def guess_field(header: str) -> tuple[str | None, float]:
    # أسماء الأعمدة بالأنظمة كثير فيها شرطات سفلية (item_name، received_by).
    # match_key بتخلّي "_" لأنها حرف كلمة، فما كانت تطابق المرادفات
    # المكتوبة بمسافة. نبدّلها قبل التطبيع.
    k = match_key(str(header or "").replace("_", " "))
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


def auto_map(headers: list[str], rows: list[list] | None = None) -> dict[str, dict]:
    """Map headers to fields. With rows, the values are checked too (see profile.py):
    each entry then also carries "review" and "evidence"."""
    names = _map_by_name(headers)
    if rows is None:
        return names
    from .profile import refine_with_values  # profile imports this module
    return refine_with_values(headers, rows, names)


def _map_by_name(headers: list[str]) -> dict[str, dict]:
    guesses = {h: guess_field(h) for h in headers}
    # نوزّع الحقول بالأقوى أولاً (التامّة قبل التقريبية) حتى لا يحجز عمود
    # تقريبي ("حالة الدفع") حقلاً يطابقه عمود آخر تماماً ("طريقة الدفع").
    # عند التعادل: أعمدة الوقت بعد غيرها (فيأخذ "التاريخ" حقل التاريخ)، ثم
    # ترتيب الأعمدة الأصلي.
    order = sorted(range(len(headers)),
                   key=lambda i: (-guesses[headers[i]][1], _is_time_header(headers[i]), i))
    used: set[str] = set()
    chosen: dict[str, tuple[str | None, float]] = {}
    for i in order:
        h = headers[i]
        f, conf = guesses[h]
        if f == "date" and "date" in used and "sale_time" not in used and _is_time_header(h):
            f = "sale_time"
        if f and f in used:
            f, conf = None, 0.0
        if f:
            used.add(f)
        chosen[h] = (f, conf)
    return {h: {"field": chosen[h][0], "confidence": round(chosen[h][1], 2),
                "source": "rules" if chosen[h][0] else None} for h in headers}


_WASTE_PREFIXES = tuple(match_key(w) for w in ("هدر", "تالف", "waste", "spoil"))
_PURCHASE_PREFIXES = tuple(match_key(w) for w in ("مورد", "مشتريات", "supplier", "vendor", "purchas"))
_PURCHASE_WORDS = {match_key(w) for w in ("شراء", "الشراء", "purchase", "purchases")}


def _header_tokens(headers: list[str] | None) -> set[str]:
    return {t for h in headers or () for t in match_key(str(h or "").replace("_", " ")).split()}


def _starts_with_any(tokens: set[str], prefixes: tuple[str, ...]) -> bool:
    return any(t.startswith(p) for t in tokens for p in prefixes)


def detect_entity(fields: set[str], headers: list[str] | None = None) -> str:
    tokens = _header_tokens(headers)
    # سجلّ هدر/تالف (صنف + كمية + تاريخ) كان يُقرأ مبيعات، فيدخل الهدر كإيراد.
    # إدراك ما بيدعم الهدر لسا، فالأسلم جدول عام لا يُستورد منه شيء.
    if _starts_with_any(tokens, _WASTE_PREFIXES) and not ({"cashier", "customer_name", "payment_method"} & fields):
        return "unknown"
    # فواتير مشتريات من مورد كانت تُقرأ مبيعات (واسم المورد كزبون) فتتسجّل
    # المشتريات كإيرادات. نعاملها كقائمة أسعار مورد: تحدّث تكلفة الأصناف فقط.
    # لا ينطبق على مبيعات فيها كاشير/زبون، ولا على كتالوج أصناف فيه مخزون.
    looks_purchase = ("supplier" in fields or _starts_with_any(tokens, _PURCHASE_PREFIXES)
                      or bool(tokens & _PURCHASE_WORDS))
    if looks_purchase and not ({"cashier", "customer_name", "stock", "minimum_stock"} & fields):
        if "product" in fields and ({"unit_price", "cost", "carton_price"} & fields):
            return "supplier_prices"
        return "unknown"
    if {"product", "quantity"} <= fields and ({"date", "invoice_number"} & fields):
        return "sales"
    if "supplier" in fields and ({"carton_price", "pack_size"} & fields):
        return "supplier_prices"
    if "product" in fields and ({"stock", "minimum_stock"} & fields):
        return "products"
    if "supplier" in fields and "cost" in fields and "stock" not in fields:
        return "supplier_prices"
    if "product" in fields and ({"unit_price", "cost", "stock", "barcode"} & fields):
        return "products"
    if {"customer_name", "phone"} & fields:
        return "customers"
    return "unknown"


def kind_of(field: str | None) -> str | None:
    return FIELDS[field][0] if field in FIELDS else None

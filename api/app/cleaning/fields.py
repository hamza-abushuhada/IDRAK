from rapidfuzz import fuzz, process

from .arabic import match_key

FIELDS: dict[str, tuple[str, list[str]]] = {
    "invoice_number": ("id", ["invoice", "invoice no", "invoice number", "inv", "inv no", "receipt", "receipt no", "bill no", "رقم الفاتورة", "فاتورة", "الفاتورة", "رقم الايصال", "transaction id"]),
    "date": ("date", ["date", "day", "sold at", "datetime", "sale date", "transaction date", "تاريخ", "التاريخ", "تاريخ البيع", "time", "الوقت"]),
    "branch": ("branch", ["branch", "store", "shop", "location", "outlet", "فرع", "الفرع", "المحل", "الموقع"]),
    "cashier": ("person", ["cashier", "employee", "staff", "user", "sales person", "كاشير", "الكاشير", "الموظف", "موظف", "البائع"]),
    "product": ("product", ["product", "item", "item name", "product name", "description", "sku name", "اسم الصنف", "الصنف", "صنف", "المنتج", "اسم المنتج", "البند", "المادة"]),
    "barcode": ("barcode", ["barcode", "ean", "upc", "باركود", "الباركود"]),
    "sku": ("id", ["sku", "item code", "code", "رمز الصنف", "كود"]),
    "category": ("category", ["category", "department", "group", "الفئة", "التصنيف", "القسم"]),
    "quantity": ("quantity", ["qty", "quantity", "units", "count", "pcs", "الكمية", "كمية", "العدد", "عدد"]),
    "unit_price": ("money", ["price", "unit price", "selling price", "sale price", "سعر الوحدة", "السعر", "سعر", "سعر البيع", "سعر الحبة"]),
    "cost": ("money", ["cost", "unit cost", "purchase price", "التكلفة", "سعر الشراء", "الكلفة"]),
    "total": ("money", ["total", "amount", "line total", "net", "net amount", "value", "الإجمالي", "الاجمالي", "المجموع", "المبلغ", "القيمة"]),
    "discount": ("money", ["discount", "disc", "خصم", "الخصم"]),
    "payment_method": ("payment", ["payment", "payment method", "pay method", "tender", "method", "طريقة الدفع", "الدفع", "وسيلة الدفع"]),
    "customer_name": ("person", ["customer", "customer name", "client", "name", "full name", "الزبون", "اسم الزبون", "العميل", "اسم العميل", "الاسم"]),
    "phone": ("phone", ["phone", "mobile", "tel", "telephone", "whatsapp", "customer phone", "phone number", "موبايل", "رقم الموبايل", "هاتف", "الهاتف", "رقم الهاتف", "جوال", "واتس"]),
    "email": ("email", ["email", "e-mail", "mail", "البريد", "البريد الالكتروني", "ايميل", "الايميل", "الإيميل"]),
    "city": ("city", ["city", "town", "المدينة", "مدينة", "المحافظة"]),
    "area": ("area", ["area", "district", "neighborhood", "neighbourhood", "region", "المنطقة", "منطقة", "الحي"]),
    "supplier": ("company", ["supplier", "vendor", "distributor", "المورد", "مورد", "الموزع"]),
    "carton_price": ("money", ["carton price", "case price", "سعر الكرتونة", "سعر الكرتونه"]),
    "pack_size": ("quantity", ["pack size", "units per case", "case qty", "عدد الحبات بالكرتونة", "عدد الحبات بالكرتونه", "عدد بالكرتونة"]),
    "stock": ("quantity", ["stock", "on hand", "inventory", "balance", "المخزون", "الرصيد", "الكمية المتوفرة"]),
    "expiry_date": ("date", ["expiry", "expiry date", "exp", "best before", "تاريخ الانتهاء", "الانتهاء", "تاريخ الصلاحية"]),
    "updated_at": ("date", ["last updated", "updated", "update date", "تاريخ آخر تحديث", "تاريخ التحديث", "اخر تحديث"]),
    "notes": ("text", ["notes", "note", "comment", "comments", "remarks", "ملاحظات", "ملاحظة"]),
    "gender": ("gender", ["gender", "sex", "الجنس"]),
}

LABELS = {
    "invoice_number": ("Invoice number", "رقم الفاتورة"), "date": ("Date", "التاريخ"), "branch": ("Branch", "الفرع"),
    "cashier": ("Cashier", "الكاشير"), "product": ("Product", "الصنف"), "barcode": ("Barcode", "الباركود"), "sku": ("SKU", "رمز الصنف"),
    "category": ("Category", "الفئة"), "quantity": ("Quantity", "الكمية"), "unit_price": ("Unit price", "سعر الوحدة"),
    "cost": ("Cost", "التكلفة"), "total": ("Total", "الإجمالي"), "discount": ("Discount", "الخصم"),
    "payment_method": ("Payment method", "طريقة الدفع"), "customer_name": ("Customer name", "اسم الزبون"), "phone": ("Phone", "الهاتف"),
    "email": ("Email", "الإيميل"), "city": ("City", "المدينة"), "area": ("Area", "المنطقة"), "supplier": ("Supplier", "المورد"),
    "carton_price": ("Carton price", "سعر الكرتونة"), "pack_size": ("Pack size", "عدد الحبات"), "stock": ("Stock", "المخزون"),
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


def guess_field(header: str) -> tuple[str | None, float]:
    k = match_key(header)
    if not k:
        return None, 0.0
    for key, f in _SYN:
        if key == k:
            return f, 1.0
    best = process.extractOne(k, _SYN_KEYS, scorer=fuzz.token_set_ratio)
    if best and best[1] >= 86:
        return _SYN[best[2]][1], best[1] / 100
    return None, 0.0


def auto_map(headers: list[str]) -> dict[str, dict]:
    used: set[str] = set()
    out = {}
    for h in headers:
        f, conf = guess_field(h)
        if f and f in used:
            f, conf = None, 0.0
        if f:
            used.add(f)
        out[h] = {"field": f, "confidence": round(conf, 2), "source": "rules" if f else None}
    return out


def detect_entity(fields: set[str]) -> str:
    if {"product", "quantity"} <= fields and ({"date", "invoice_number"} & fields):
        return "sales"
    if "supplier" in fields and ({"unit_price", "carton_price", "cost"} & fields):
        return "supplier_prices"
    if "product" in fields and ({"unit_price", "cost", "stock", "barcode"} & fields):
        return "products"
    if {"customer_name", "phone"} & fields:
        return "customers"
    return "unknown"


def kind_of(field: str | None) -> str | None:
    return FIELDS[field][0] if field in FIELDS else None

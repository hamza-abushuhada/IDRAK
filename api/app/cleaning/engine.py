from __future__ import annotations

import datetime as dt
import statistics
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from rapidfuzz import fuzz, process

from . import bilingual as B
from . import money as M
from . import parsers as P
from .arabic import clean_text, is_arabic, is_null, match_key, nums, place_key, skeleton, smart_title
from .fields import REQUIRED, STANDS_IN, detect_entity, kind_of

_PLAIN_NUMBER = re.compile(r"-?[0-9]+(\.[0-9]+)?")

RULES = {
    "arabic_digits": ("Arabic-Indic digits converted (١٢٣ → 123)", "تحويل الأرقام الهندية (١٢٣) إلى أرقام عادية", "standardize"),
    "whitespace": ("Extra spaces & invisible characters removed", "إزالة المسافات الزائدة والرموز المخفية", "standardize"),
    "null_token": ("Placeholder values cleared (N/A, -, ؟)", "مسح القيم الوهمية مثل N/A و - و ؟", "standardize"),
    "date_format": ("Dates standardized to YYYY-MM-DD", "توحيد صيغة التواريخ إلى YYYY-MM-DD", "format"),
    "excel_date": ("Excel serial numbers converted to dates", "تحويل أرقام إكسل إلى تواريخ", "format"),
    "hijri_date": ("Hijri dates converted to Gregorian", "تحويل التواريخ الهجرية إلى ميلادية", "format"),
    "money_format": ("Currency text removed from amounts (JD, د.ا)", "إزالة رموز العملة من المبالغ (JD، د.ا)", "format"),
    "fils_to_jd": ("Amounts converted from fils to JOD using the import settings", "تحويل المبالغ من فلس إلى دينار حسب إعدادات الاستيراد", "format"),
    "fils_detected": ("Amounts written in fils converted to JOD (3250 → 3.250)", "مبالغ مكتوبة بالفلس تحوّلت لدينار (3250 ← 3.250)", "fix"),
    "decimal_comma": ("Decimal commas fixed (0,350 → 0.350)", "تصحيح الفاصلة العشرية (0,350 ← 0.350)", "format"),
    "quantity_format": ("Quantities converted to plain numbers", "تحويل الكميات إلى أرقام", "format"),
    "phone_e164": ("Phone numbers standardized to +962 format", "توحيد أرقام الهواتف بصيغة 962+", "format"),
    "email_fix": ("Email typos fixed (gmial → gmail)", "تصحيح أخطاء الإيميلات (gmial ← gmail)", "fix"),
    "payment_map": ("Payment methods unified (كاش / Cash / نقدي → cash)", "توحيد طرق الدفع (كاش / Cash / نقدي)", "merge"),
    "city_map": ("City names unified (عمّان / AMMAN → Amman)", "توحيد أسماء المدن", "merge"),
    "branch_map": ("Branch name variants unified", "توحيد أسماء الفروع", "merge"),
    "product_match": ("Product name variants merged (بيبسي 330 / PEPSI 330ML)", "دمج أسماء الصنف المختلفة لصنف واحد", "merge"),
    "person_match": ("Name variants merged across Arabic & English", "دمج تهجئات الأسماء بين العربي والإنجليزي", "merge"),
    "value_merge": ("Similar spellings merged", "دمج التهجئات المتشابهة", "merge"),
    "title_case": ("Capitalization fixed", "تصحيح الأحرف الكبيرة والصغيرة", "standardize"),
    "id_format": ("Invoice numbers cleaned (spaces, case, digits)", "تنظيف أرقام الفواتير", "standardize"),
    "duplicate_row": ("Duplicate rows removed", "حذف الصفوف المكررة", "dedupe"),
    "blank_row": ("Empty rows removed", "حذف الصفوف الفارغة", "dedupe"),
    "memory": ("Applied rules Idrak learned from you", "تطبيق قواعد التنظيف اللي تعلّمها إدراك منك", "memory"),
    "gender_map": ("Gender values unified", "توحيد قيم الجنس", "merge"),
}
FLAGS = {
    "invalid_phone": ("Phone numbers that can't be valid", "أرقام هواتف غير صالحة"),
    "invalid_date": ("Dates that can't be read", "تواريخ غير مفهومة"),
    "invalid_number": ("Numbers that can't be read", "أرقام غير مفهومة"),
    "invalid_email": ("Invalid emails", "إيميلات غير صالحة"),
    "unknown_payment": ("Unknown payment methods", "طرق دفع غير معروفة"),
    "negative_qty": ("Negative quantities (returns?)", "كميات سالبة (مرتجعات؟)"),
    "qty_outlier": ("Suspicious quantities (e.g. 999)", "كميات مشبوهة (مثل 999)"),
    "future_date": ("Dates in the future", "تواريخ بالمستقبل"),
    "invalid_time": ("Times that can't be read", "أوقات غير مفهومة"),
    "missing_required": ("Missing required values", "قيم أساسية ناقصة"),
    "unknown_product": ("Products not in your catalog", "أصناف غير موجودة بقائمتك"),
    "missing_total": ("Line total is missing", "إجمالي السطر ناقص"),
    "total_mismatch": ("Line total does not match quantity × unit price", "إجمالي السطر لا يطابق الكمية × سعر الوحدة"),
    "money_outlier": ("Amounts far out of scale (fils or a typo?)", "مبالغ بعيدة جداً عن الباقي (فلس أو غلطة؟)"),
}
PRIORITY = ["memory", "fils_to_jd", "fils_detected", "product_match", "person_match", "branch_map", "payment_map", "city_map",
            "value_merge", "hijri_date", "excel_date", "email_fix", "phone_e164", "date_format", "decimal_comma", "money_format",
            "quantity_format", "arabic_digits", "id_format", "title_case", "gender_map", "null_token", "whitespace"]
CATEGORICAL = {"product", "person", "branch", "payment", "city", "area", "category", "company", "gender"}
WEIGHTS = {"completeness": 0.25, "validity": 0.30, "uniqueness": 0.15, "consistency": 0.20, "timeliness": 0.10}


@dataclass
class Change:
    row: int
    column: str
    old: str
    new: str
    rule: str
    category: str
    confidence: float = 1.0
    group: str | None = None


@dataclass
class Flag:
    row: int
    column: str
    value: str
    reason: str


@dataclass
class Context:
    products: list[dict] = field(default_factory=list)
    branches: list[dict] = field(default_factory=list)
    employees: list[dict] = field(default_factory=list)
    rules: dict = field(default_factory=dict)


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _fmt_num(x: float, money: bool) -> str:
    if money:
        return f"{x:.3f}"
    return str(int(x)) if float(x).is_integer() else f"{x:.3f}".rstrip("0").rstrip(".")


# Words that say what kind of business a name is, or how much of a product, not
# which one (already in match_key form). Fuzzy "one shared word is enough" matching
# merged "Al Wafa Trading" into "Al Najah Food" (both "al") and a garlic sack into
# "Mixed Grill 1kg" (both "kg"); these words never count as the shared one.
GENERIC = frozenset("""
    al el the co company est establishment trading trade traders import imports export distribution dist
    distributors food foods supplies supply group jordan jordanian international intl ltd llc inc factory
    industries of and for with
    شركه موسسه تجاره للتجاره لتجاره تجاريه توزيع للتوزيع استيراد تصدير مواد للمواد غذاييه اغذيه للاغذيه
    توريدات للتوريدات مجموعه اردن اردني اردنيه دوليه مصنع مصانع صناعات لصناعه مع و ذ م
    ml l g kg pc can ctn
""".split())


def core_words(mk: str) -> list[str]:
    """The words of a match_key that tell one name from another."""
    return [t for t in mk.split() if t not in GENERIC and not t.replace(".", "").isdigit()]


def subset_match(a: str, b: str) -> bool:
    """Every distinctive word of the shorter name is in the longer one (spelling slips allowed).

    "Al Maha Dairy" ~ "Al Maha Dairy Jordan", "الرائد تجارة" ~ "مؤسسة الرائد التجارية";
    but not "Al Wafa Trading" ~ "Al Najah Food", nor "خبز شاورما" ~ "وجبة شاورما لحم".
    """
    ca, cb = core_words(a), core_words(b)
    if not ca or not cb:
        return False
    short, long_ = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    if sum(len(t) for t in short) < 4:
        return False
    return all(any(t == u or (min(len(t), len(u)) >= 4 and fuzz.ratio(t, u) >= 85) for u in long_) for t in short)


class Matcher:
    def __init__(self, entries: list[dict], loose: bool = False, places: bool = False):
        self.entries = entries
        self.loose = loose
        self.keys, self.owner, self.skel, self.knums = [], [], {}, []
        self.exact: dict[str, int] = {}
        # Branches: every spelling of the same place is an exact match ("فرع خلدا" = "Khalda").
        self.places: dict[str, int] = {}
        for i, e in enumerate(entries):
            for k in e["keys"]:
                if places and match_key(k):
                    self.places.setdefault(place_key(k), i)
                mk = match_key(k)
                if mk:
                    self.keys.append(mk)
                    self.owner.append(i)
                    self.knums.append(nums(k))
                    self.exact.setdefault(mk, i)
                sk = skeleton(k)
                if sk:
                    self.skel.setdefault(sk, i)

    def match(self, value: str):
        k = match_key(value)
        if not k or not self.keys:
            return None, 0
        if k in self.exact:
            return self.entries[self.exact[k]]["name"], 1.0
        if self.places and (pk := place_key(value)) in self.places:
            return self.entries[self.places[pk]]["name"], 0.95
        vn = nums(value)
        cands = [i for i, kn in enumerate(self.knums) if kn == vn] if vn else list(range(len(self.keys)))
        if not cands:
            return None, 0
        ckeys = [self.keys[i] for i in cands]
        best = process.extractOne(k, ckeys, scorer=fuzz.token_sort_ratio)
        if best and best[1] >= 82:
            return self.entries[self.owner[cands[best[2]]]]["name"], round(best[1] / 100, 2)
        sk = skeleton(value)
        if sk in self.skel and nums(self.entries[self.skel[sk]]["name"]) == vn:
            return self.entries[self.skel[sk]]["name"], 0.8
        # One name inside the other ("بيبسي" in "بيبسي 330 مل علبة"). partial_token_set_ratio
        # alone scores 100 on a single shared word, so it only shortlists; subset_match
        # decides, and two different catalog products matching means it's ambiguous.
        if len(k) >= 4:
            shortlist = process.extract(k, ckeys, scorer=fuzz.partial_token_set_ratio,
                                        score_cutoff=90 if self.loose else 95, limit=25)
            owners = {self.owner[cands[i]] for _, _, i in shortlist if subset_match(k, ckeys[i])}
            if len(owners) == 1:
                return self.entries[owners.pop()]["name"], 0.7
        return None, 0


def cluster_values(values: Counter, kind: str = "product") -> dict[str, tuple[str, float]]:
    """يجمع الأشكال المتقاربة من نفس القيمة تحت اسم واحد.

    كان يمرّ على كل مجموعة لكل قيمة: O(n²) مع حساب تشابه نصّي لكل زوج.
    على ملف فيه آلاف القيم الفريدة (أصناف/زبائن) هذا بياخد دقائق ويقطع
    الطلب. صار: مطابقة تامة عبر قاموس، ثم بحث ضبابي داخل مجموعة الأرقام
    فقط وبعد فحص أول حرف — نفس النتيجة بجزء بسيط من الوقت.
    """
    groups: list[dict] = []
    loose = kind in ("branch", "city", "area", "company")
    # مجموعات مفهرسة: بالأرقام (شرط أساسي أصلاً بالمطابقة) ثم بالحرف الأول.
    by_nums: dict[str, dict[str, list[dict]]] = {}
    exact: dict[str, dict] = {}
    for raw, cnt in values.most_common():
        disp = clean_text(raw)
        if not disp:
            continue
        mk, sk, nm, ar = match_key(disp), skeleton(disp), tuple(nums(disp)), is_arabic(disp)
        if kind == "branch":
            mk = place_key(disp)  # "Khalda", "خلدا", "فرع خلدا" are one exact key
        target, conf = exact.get(mk), 1.0
        # Business names bucket by their first distinctive word, so "مؤسسة الرائد"
        # meets "الرائد تجارة" (they start with different letters).
        bucket_key = " ".join(core_words(mk)) or mk if loose else mk
        if target is None:
            buckets = by_nums.setdefault(nm, {})
            first = bucket_key[:1]
            # buckets.get() بترجّع قائمة لو المفتاح موجود و tuple افتراضي
            # لو مش موجود — جمعهم مع بعض كان يفشل. نطبيع الحالتين لقائمة.
            cands = list(buckets.get(first, []))
            if first:
                cands += buckets.get("", [])
            for g in cands:
                if len(mk) > 4 and fuzz.ratio(mk, g["mk"]) >= (90 if loose else 93):
                    target, conf = g, 0.9
                    break
                if sk and sk == g["sk"] and ar != g["ar"] and len(sk.replace(" ", "")) >= (3 if loose else 4):
                    target, conf = g, 0.8
                    break
            if target is None and loose:
                # "Irbid" inside "Irbid - University St" merges only when it fits one group:
                # with two Irbid branches a bare "Irbid" can't be placed.
                fits = [g for g in cands if min(len(mk), len(g["mk"])) >= 4 and subset_match(mk, g["mk"])]
                if len({id(g) for g in fits}) == 1:
                    target, conf = fits[0], 0.75
        if target is None:
            g = {"mk": mk, "sk": sk, "nums": nm, "ar": ar, "canon": disp, "members": [(raw, 1.0, cnt)]}
            groups.append(g)
            by_nums.setdefault(nm, {}).setdefault(bucket_key[:1], []).append(g)
            exact[mk] = g
        else:
            target["members"].append((raw, conf, cnt))
    out = {}
    for g in groups:
        canon = g["canon"]
        if not is_arabic(canon):
            canon = smart_title(canon)
        for raw, conf, _ in g["members"]:
            out[raw] = (canon, conf)
    return out


def run(headers: list[str], rows: list[list], mapping: dict[str, str | None], ctx: Context | None = None,
        today: dt.date | None = None, price_unit: str = "jd", date_order: str = "auto",
        entity: str | None = None) -> dict:
    ctx = ctx or Context()
    today = today or dt.date.today()
    fields = {h: mapping.get(h) for h in headers}
    # The type the user confirmed on the mapping screen wins over detection.
    if entity not in REQUIRED:
        entity = detect_entity({f for f in fields.values() if f}, headers)
    col_idx = {h: i for i, h in enumerate(headers)}
    n = len(rows)
    raw = [[_s(r[i]) if i < len(r) else "" for i in range(len(headers))] for r in rows]
    clean = [list(r) for r in raw]
    changes: list[Change] = []
    flags: list[Flag] = []
    cell_rules: dict[tuple[int, int], list[str]] = defaultdict(list)
    clusters: list[dict] = []

    def record(ri, ci, new, rule, conf=1.0, group=None):
        if rule:
            cell_rules[(ri, ci)].append(rule)
        if new is None:
            new = ""
        if new != clean[ri][ci]:
            clean[ri][ci] = new
        if rule and new != raw[ri][ci]:
            pass

    blank = {ri for ri, r in enumerate(raw) if all(not clean_text(v) for v in r)}

    def number(ri, ci):
        cell = rows[ri][ci] if ci < len(rows[ri]) else None
        return P.parse_number(cell if isinstance(cell, (int, float)) else raw[ri][ci])[0]

    # Fils mixed into dinar columns (cleaning/money.py), decided across columns:
    # a product's other rows, quantity x price and cost vs price all count.
    fils_fix: dict[str, dict[int, float]] = {}
    fils_review: dict[str, set[int]] = {}
    if price_unit != "fils":
        money_cols = {f: [number(ri, col_idx[h]) for ri in range(n)]
                      for h, f in fields.items() if kind_of(f) == "money"}
        if money_cols:
            prod_h = next((x for x, ff in fields.items() if ff == "product"), None)
            qty_h = next((x for x, ff in fields.items() if ff == "quantity"), None)
            fils_fix, fils_review = M.detect(
                money_cols,
                [match_key(raw[ri][col_idx[prod_h]]) or None for ri in range(n)] if prod_h else None,
                [number(ri, col_idx[qty_h]) for ri in range(n)] if qty_h else None)

    for h in headers:
        ci, f = col_idx[h], fields[h]
        kind = kind_of(f)
        vals = [raw[ri][ci] for ri in range(n)]
        if kind is None:
            for ri in range(n):
                c = clean_text(vals[ri])
                if c != vals[ri]:
                    record(ri, ci, c, "arabic_digits" if P.has_arabic_digits(vals[ri]) else "whitespace")
            continue

        if kind == "date":
            dayfirst = P.column_dayfirst(vals) if date_order == "auto" else date_order != "mdy"
            for ri in range(n):
                if ri in blank:
                    continue
                d, rule = P.parse_date(rows[ri][ci] if ci < len(rows[ri]) and isinstance(rows[ri][ci], (int, float, dt.date)) else vals[ri], dayfirst)
                if d is None:
                    if rule == "invalid_date":
                        flags.append(Flag(ri, h, vals[ri], "invalid_date"))
                    elif rule == "null_token":
                        record(ri, ci, "", "null_token")
                    continue
                if d.date() > today + dt.timedelta(days=1) and isinstance(vals[ri], str):
                    # 08/12/2026 read day-first is in the future (8 Dec) but month-first
                    # is a past day (12 Aug): a sale can't be in the future, so take the
                    # reading that isn't. Only when both readings are valid dates.
                    alt, alt_rule = P.parse_date(vals[ri], not dayfirst)
                    if alt is not None and alt.date() != d.date() and alt.date() <= today + dt.timedelta(days=1):
                        d, rule = alt, alt_rule or "date_format"
                if d.date() > today + dt.timedelta(days=1):
                    flags.append(Flag(ri, h, vals[ri], "future_date"))
                record(ri, ci, P.fmt_date(d), rule)

        elif kind == "time":
            for ri in range(n):
                if ri in blank:
                    continue
                t, rule = P.parse_time(vals[ri])
                if t is None:
                    if rule == "invalid_time":
                        flags.append(Flag(ri, h, vals[ri], "invalid_time"))
                    elif rule == "null_token":
                        record(ri, ci, "", "null_token")
                    continue
                record(ri, ci, t, rule or "time_format")

        elif kind in ("money", "quantity"):
            parsed = []
            for ri in range(n):
                v, rule = P.parse_number(rows[ri][ci] if ci < len(rows[ri]) and isinstance(rows[ri][ci], (int, float)) else vals[ri])
                parsed.append((v, rule))
            good = [v for v, _ in parsed if v is not None and v > 0]
            med = statistics.median(good) if good else 0
            for ri, (v, rule) in enumerate(parsed):
                if ri in blank:
                    continue
                if v is None:
                    if rule == "percent":
                        continue
                    if rule == "invalid_number":
                        flags.append(Flag(ri, h, vals[ri], "invalid_number"))
                    elif rule == "null_token":
                        record(ri, ci, "", "null_token")
                    continue
                conf = 1.0
                if kind == "money" and price_unit == "fils":
                    v, rule = v / 1000, "fils_to_jd"
                elif kind == "money" and M.FILS_WORD.search(vals[ri]):
                    v, rule = v / 1000, "fils_detected"  # "500 فلس" says so itself
                elif kind == "money" and ri in fils_fix.get(f, {}):
                    v, rule, conf = fils_fix[f][ri], "fils_detected", 0.9
                elif kind == "money" and ri in fils_review.get(f, set()):
                    flags.append(Flag(ri, h, vals[ri], "money_outlier"))
                if kind == "quantity":
                    if v < 0:
                        flags.append(Flag(ri, h, vals[ri], "negative_qty"))
                    elif med and v > max(50, med * 40):
                        flags.append(Flag(ri, h, vals[ri], "qty_outlier"))
                new = _fmt_num(v, kind == "money")
                if rule is None and new != vals[ri]:
                    if _PLAIN_NUMBER.fullmatch(vals[ri]) and float(vals[ri]) == v:
                        # The same number, only written with fewer decimals ("3.25" vs
                        # "3.250"): the cell reads the same on import. Kept as a change it
                        # was a third of a big file's review list (152,000 cells out of
                        # 470,000) and of what got saved.
                        record(ri, ci, new, None)
                        continue
                    rule = "money_format" if kind == "money" else "quantity_format"
                record(ri, ci, new, rule, conf)

        elif kind == "phone":
            for ri in range(n):
                if ri in blank:
                    continue
                v, rule = P.parse_phone(vals[ri])
                if v is None:
                    if rule == "invalid_phone":
                        flags.append(Flag(ri, h, vals[ri], "invalid_phone"))
                    elif rule == "null_token":
                        record(ri, ci, "", "null_token")
                    continue
                record(ri, ci, v, rule)

        elif kind == "email":
            for ri in range(n):
                if ri in blank:
                    continue
                v, rule = P.parse_email(vals[ri])
                if v is None:
                    if rule == "invalid_email":
                        flags.append(Flag(ri, h, vals[ri], "invalid_email"))
                    elif rule == "null_token":
                        record(ri, ci, "", "null_token")
                    continue
                record(ri, ci, v, rule)

        elif kind == "id":
            for ri in range(n):
                c = clean_text(vals[ri]).upper().replace(" ", "")
                if c != vals[ri]:
                    record(ri, ci, c, "arabic_digits" if P.has_arabic_digits(vals[ri]) else "id_format")

        elif kind in CATEGORICAL or kind == "text":
            counts = Counter(vals[ri] for ri in range(n) if ri not in blank and clean_text(vals[ri]) and not is_null(vals[ri]))
            mapping_v: dict[str, tuple[str, str, float]] = {}
            matcher = None
            match_rule = {"product": "product_match", "person": "person_match", "branch": "branch_map"}.get(kind, "value_merge")
            if kind == "product" and ctx.products:
                matcher = Matcher(ctx.products)
            elif kind == "branch" and ctx.branches:
                matcher = Matcher(ctx.branches, loose=True, places=True)
            elif kind == "person" and f == "cashier" and ctx.employees:
                matcher = Matcher(ctx.employees)
            fallback = cluster_values(counts, kind) if kind in ("product", "person", "branch", "area", "category", "company") else {}
            unknown: set[str] = set()
            for v in counts:
                mk = match_key(v)
                if (kind, mk) in ctx.rules:
                    mapping_v[v] = (ctx.rules[(kind, mk)], "memory", 1.0)
                    continue
                if kind == "payment":
                    out, rule = P.map_payment(v)
                    mapping_v[v] = (out or clean_text(v), rule, 1.0)
                    continue
                if kind == "city":
                    out, rule = P.map_city(v)
                    mapping_v[v] = (out, rule, 1.0)
                    continue
                if kind == "gender":
                    k = match_key(v)
                    out = "M" if k in ("m", "male", "ذكر", "رجل") else "F" if k in ("f", "female", "انثي", "انثى", "أنثى", "امراه") else clean_text(v)
                    mapping_v[v] = (out, "gender_map" if out != v else None, 1.0)
                    continue
                if kind == "text":
                    c = clean_text(v)
                    mapping_v[v] = (c, ("arabic_digits" if P.has_arabic_digits(v) else "whitespace") if c != v else None, 1.0)
                    continue
                canon, conf = (matcher.match(v) if matcher else (None, 0))
                if canon is None:
                    canon, conf = fallback.get(v, (clean_text(v), 1.0))
                    if matcher and kind == "product":
                        unknown.add(v)
                c = clean_text(v)
                if canon == c:
                    rule = None if c == v else ("arabic_digits" if P.has_arabic_digits(v) else "whitespace")
                elif match_key(canon) == match_key(c) and canon.lower() == c.lower():
                    rule = "title_case"
                else:
                    rule = match_rule
                mapping_v[v] = (canon, rule, conf)
            for ri in range(n):
                v = vals[ri]
                if ri in blank:
                    continue
                if not clean_text(v):
                    continue
                if is_null(v):
                    record(ri, ci, "", "null_token")
                    continue
                canon, rule, conf = mapping_v.get(v, (clean_text(v), None, 1.0))
                if kind == "payment" and rule == "unknown_payment":
                    flags.append(Flag(ri, h, v, "unknown_payment"))
                    record(ri, ci, clean_text(v), None)
                    continue
                if v in unknown:
                    flags.append(Flag(ri, h, v, "unknown_product"))
                record(ri, ci, canon, rule, conf, group=f"{h}::{canon}" if rule in ("product_match", "person_match", "branch_map", "value_merge", "payment_map", "city_map", "memory") else None)
            groups = defaultdict(Counter)
            for v, (canon, rule, conf) in mapping_v.items():
                groups[canon][v] += counts[v]
            for canon, members in groups.items():
                if len(members) > 1:
                    clusters.append({"column": h, "field": f, "canonical": canon,
                                     "variants": [{"value": m, "count": c} for m, c in members.most_common()],
                                     "rows": sum(members.values())})

    _pair_languages(headers, fields, col_idx, clean, blank, ctx, record, clusters)

    qi = next((col_idx[x] for x, ff in fields.items() if ff == "quantity"), None)
    pi = next((col_idx[x] for x, ff in fields.items() if ff == "unit_price"), None)
    ti = next((col_idx[x] for x, ff in fields.items() if ff == "total"), None)
    di = next((col_idx[x] for x, ff in fields.items() if ff == "discount"), None)
    if qi is not None and pi is not None and ti is not None:
        for ri in range(n):
            if ri in blank:
                continue
            try:
                q = Decimal(clean[ri][qi])
                p = Decimal(clean[ri][pi])
            except (InvalidOperation, TypeError):
                continue
            if q <= 0 or q > 200:
                continue
            exp = (q * p).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
            if exp > 2000:
                continue
            t = clean[ri][ti]
            # An empty total with a quantity and a price isn't a problem: the import
            # computes the line from them. Flagging it put 1,390 rows in front of the
            # user (and dropped them) for nothing.
            if not t:
                continue
            try:
                tv = Decimal(t)
            except (ValueError, InvalidOperation):
                # InvalidOperation تُرفع من Decimal() لما تكون القيمة
                # نصاً غير رقمي — وما كانت ملتقطة، فكانت تُسقط الملف كله.
                flags.append(Flag(ri, headers[ti], t, "invalid_number"))
                continue
            draw = clean[ri][di].strip() if di is not None and clean[ri][di] else ""
            try:
                disc = (exp * Decimal(draw[:-1]) / 100 if draw.endswith("%") else Decimal(draw)) if draw else Decimal("0")
            except (InvalidOperation, TypeError):
                disc = Decimal("0")
            if not _total_explained(tv, exp, disc):
                flags.append(Flag(ri, headers[ti], t, "total_mismatch"))

    for (ri, ci), rules in cell_rules.items():
        if clean[ri][ci] == raw[ri][ci]:
            continue
        rs = [r for r in rules if r in RULES]
        if not rs:
            rs = ["whitespace"]
        rule = min(rs, key=lambda r: PRIORITY.index(r) if r in PRIORITY else 99)
        h = headers[ci]
        grp = None
        if rule in ("product_match", "person_match", "branch_map", "value_merge", "payment_map", "city_map", "memory"):
            grp = f"{h}::{clean[ri][ci]}"
        conf = 1.0
        changes.append(Change(ri, h, raw[ri][ci], clean[ri][ci], rule, RULES[rule][2], conf, grp))

    seen = {}
    dup = set()
    for ri in range(n):
        if ri in blank:
            continue
        key = tuple(clean[ri])
        if key in seen:
            dup.add(ri)
        else:
            seen[key] = ri
    for ri in sorted(blank):
        changes.append(Change(ri, "*", "(empty row)", "", "blank_row", "dedupe"))
    for ri in sorted(dup):
        changes.append(Change(ri, "*", " | ".join(raw[ri][:5]), f"duplicate of row {seen[tuple(clean[ri])] + 2}", "duplicate_row", "dedupe"))

    for f in REQUIRED.get(entity, []):
        h = next((x for x, ff in fields.items() if ff == f), None)
        if h is None:
            continue
        ci = col_idx[h]
        # A value another column stands in for isn't missing: a sale's unit price
        # comes from its line total, a purchase's from the carton price or total.
        # A category replaces the item only in a file with no item column at all
        # (we are past that here: this column is the item), never row by row.
        stand_ins = [] if (entity, f) == ("sales", "product") else \
            [col_idx[x] for x, ff in fields.items() if ff in STANDS_IN.get((entity, f), ())]
        for ri in range(n):
            if ri in blank or ri in dup:
                continue
            if not clean[ri][ci] and not any(clean[ri][si] for si in stand_ins):
                flags.append(Flag(ri, h, "", "missing_required"))

    removed = blank | dup
    score_before = score(headers, raw, fields, entity, today, cleaned=False)
    kept = [clean[ri] for ri in range(n) if ri not in removed]
    score_after = score(headers, kept, fields, entity, today, cleaned=True)

    issues = summarize(changes, flags)
    return {
        "entity": entity,
        "headers": headers,
        "mapping": fields,
        "rows_before": n,
        "rows_after": len(kept),
        "score_before": score_before,
        "score_after": score_after,
        "changes": [asdict(c) for c in changes],
        "flags": [asdict(fl) for fl in flags],
        "issues": issues,
        "clusters": sorted(clusters, key=lambda c: -c["rows"])[:60],
        "clean_rows": kept,
        "removed_rows": sorted(removed),
    }


# Sales tax rates a line total may already include (Jordan's general rate is 16%).
TAX_RATES = (Decimal("0"), Decimal("0.16"), Decimal("0.08"), Decimal("0.04"), Decimal("0.10"))


def _close(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= Decimal("0.011") or abs(a - b) <= Decimal("0.02") * max(abs(b), Decimal("0.001"))


def _total_explained(total: Decimal, expected: Decimal, discount: Decimal = Decimal("0")) -> bool:
    """Does quantity x price, less the discount, plus a usual tax rate give this total?

    POS exports often show the line total with 16% tax or after the discount; those
    were flagged "doesn't match" (1,584 rows of one file) though nothing was wrong.
    """
    for base in {expected, expected - discount}:
        if base <= 0:
            continue
        if any(_close(total, (base * (1 + r)).quantize(Decimal("0.001"))) for r in TAX_RATES):
            return True
    return False


def _pair_languages(headers, fields, col_idx, clean, blank, ctx, record, clusters) -> None:
    """English and Arabic names of one dish become one product (cleaning/bilingual.py).

    Runs on the cleaned values, so prices compare after fils are fixed. Each
    pairing is a "product_match" change the user reviews like any other merge.
    """
    prod_h = next((x for x, ff in fields.items() if ff == "product"), None)
    price_h = next((x for x, ff in fields.items() if ff == "unit_price"), None)
    if not prod_h or not price_h:
        return
    cat_h = next((x for x, ff in fields.items() if ff == "category"), None)
    pci, prci = col_idx[prod_h], col_idx[price_h]
    names: dict[str, dict] = {}
    for ri, row in enumerate(clean):
        if ri in blank or not row[pci]:
            continue
        d = names.setdefault(row[pci], {"prices": [], "cats": Counter(), "rows": []})
        d["rows"].append(ri)
        try:
            d["prices"].append(float(row[prci]))
        except (TypeError, ValueError):
            pass
        if cat_h and row[col_idx[cat_h]]:
            d["cats"][row[col_idx[cat_h]]] += 1

    def summary(d):
        return (statistics.median(d["prices"]) if d["prices"] else None,
                d["cats"].most_common(1)[0][0] if d["cats"] else None)

    english = {nm: summary(d) for nm, d in names.items() if not is_arabic(nm)}
    if not english:
        return
    arabic = {nm: summary(d) for nm, d in names.items() if is_arabic(nm)}
    for p in ctx.products:  # the catalog's Arabic names count too, at their saved price
        if is_arabic(p["name"]) and p.get("price") and p["name"] not in arabic:
            arabic[p["name"]] = (float(p["price"]), None)
    for en, (ar, sc) in B.pair(english, arabic).items():
        for ri in names[en]["rows"]:
            record(ri, pci, ar, "product_match", sc, group=f"{prod_h}::{ar}")
        clusters.append({"column": prod_h, "field": "product", "canonical": ar,
                         "variants": [{"value": ar, "count": len(names.get(ar, {}).get("rows", []))},
                                      {"value": en, "count": len(names[en]["rows"])}],
                         "rows": len(names.get(ar, {}).get("rows", [])) + len(names[en]["rows"])})


def _valid(kind: str, v: str, cleaned: bool) -> bool:
    if kind == "date":
        return bool(P.ISO_DATE.match(v))
    if kind in ("money", "quantity"):
        return bool(P.NUM_RE.match(v))
    if kind == "phone":
        return bool(P.E164.match(v))
    if kind == "email":
        return bool(P.EMAIL.match(v))
    if kind == "payment":
        return v in ("cash", "card", "cliq", "wallet", "online")
    if kind == "id":
        return v == v.strip() and not P.has_arabic_digits(v) and v == v.upper()
    return v == clean_text(v)


# مؤشر الصحة رقم إحصائي، مش محاسبة. حسابه على كل صفّ كان ياخد 92% من
# وقت التنظيف (26 ثانية من 28 لملف 5 آلاف صف)، فيستحيل نخدم ملف 100 ألف.
# عيّنة موزّعة على الملف كلّه تعطي نفس الرقم تقريباً بتكلفة ثابتة.
SCORE_SAMPLE = 4000


def score(headers, rows, fields, entity, today, cleaned: bool) -> dict:
    n = len(rows)
    if n == 0:
        return {"score": 0, "dimensions": {k: 0 for k in WEIGHTS}}
    if n > SCORE_SAMPLE:
        step = max(1, n // SCORE_SAMPLE)
        rows = rows[::step]
        n = len(rows)
    req = set(REQUIRED.get(entity, []))
    col_idx = {h: i for i, h in enumerate(headers)}
    filled = total_req = 0
    valid = nonempty = 0
    consistent = cat_total = 0
    timely = dated = 0
    healthy = cells = 0
    blank_rows = sum(1 for r in rows if all(not clean_text(v) for v in r))
    dups = n - len({tuple(r) for r in rows})
    for h, f in fields.items():
        if not f:
            continue
        kind = kind_of(f)
        ci = col_idx[h]
        col = [r[ci] if ci < len(r) else "" for r in rows]
        if kind in CATEGORICAL:
            vc = Counter(match_key(v) for v in col if clean_text(v))
            reps = {}
            for v in col:
                if clean_text(v):
                    reps.setdefault(match_key(v), Counter())[v] += 1
            sk_groups = defaultdict(set)
            for v in col:
                if clean_text(v):
                    sk_groups[skeleton(v) or match_key(v)].add(v)
        for v in col:
            empty = not clean_text(v) or is_null(v)
            if f in req:
                total_req += 1
                filled += not empty
            if empty:
                if f in req:
                    cells += 1
                continue
            nonempty += 1
            ok = _valid(kind, v, cleaned)
            valid += ok
            cons = True
            if kind in CATEGORICAL:
                cat_total += 1
                variants = sk_groups[skeleton(v) or match_key(v)]
                cons = len(variants) == 1
                consistent += cons
            if kind == "date" and ok:
                dated += 1
                try:
                    d = dt.date.fromisoformat(v[:10])
                    timely += (dt.date(2000, 1, 1) <= d <= today + dt.timedelta(days=1))
                except ValueError:
                    pass
            elif kind == "date":
                dated += 1
            cells += 1
            healthy += ok and cons
    dims = {
        "completeness": 100 * filled / total_req if total_req else 100.0,
        "validity": 100 * valid / nonempty if nonempty else 100.0,
        "uniqueness": 100 * (1 - (dups + blank_rows) / n),
        "consistency": 100 * consistent / cat_total if cat_total else 100.0,
        "timeliness": 100 * timely / dated if dated else 100.0,
    }
    weighted = sum(dims[k] * w for k, w in WEIGHTS.items())
    healthy_rate = 100 * healthy / cells if cells else 100
    s = 0.7 * healthy_rate + 0.3 * weighted
    s *= (dims["uniqueness"] / 100) ** 1.5 * (dims["completeness"] / 100) ** 0.5
    return {"score": round(max(0, min(100, s)), 1), "dimensions": {k: round(v, 1) for k, v in dims.items()}}


def summarize(changes: list[Change], flags: list[Flag]) -> list[dict]:
    by = defaultdict(list)
    for c in changes:
        by[c.rule].append(c)
    out = []
    for rule, cs in by.items():
        en, ar, cat = RULES[rule]
        ex, seen = [], set()
        for c in cs:
            if (c.old, c.new) in seen:
                continue
            seen.add((c.old, c.new))
            ex.append({"before": c.old, "after": c.new, "column": c.column})
            if len(ex) >= 4:
                break
        out.append({"key": rule, "kind": "fix", "title_en": en, "title_ar": ar, "category": cat, "count": len(cs), "examples": ex})
    fb = defaultdict(list)
    for fl in flags:
        fb[fl.reason].append(fl)
    for reason, fs in fb.items():
        en, ar = FLAGS[reason]
        ex = []
        for fl in fs[:4]:
            ex.append({"before": fl.value, "after": "⚠", "column": fl.column})
        out.append({"key": reason, "kind": "flag", "title_en": en, "title_ar": ar, "category": "review", "count": len(fs), "examples": ex})
    return sorted(out, key=lambda x: (x["kind"] == "flag", -x["count"]))

from __future__ import annotations

import datetime as dt
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field

from rapidfuzz import fuzz, process

from . import parsers as P
from .arabic import clean_text, is_arabic, is_null, match_key, nums, skeleton, smart_title
from .fields import REQUIRED, detect_entity, kind_of

RULES = {
    "arabic_digits": ("Arabic-Indic digits converted (١٢٣ → 123)", "تحويل الأرقام الهندية (١٢٣) إلى أرقام عادية", "standardize"),
    "whitespace": ("Extra spaces & invisible characters removed", "إزالة المسافات الزائدة والرموز المخفية", "standardize"),
    "null_token": ("Placeholder values cleared (N/A, -, ؟)", "مسح القيم الوهمية مثل N/A و - و ؟", "standardize"),
    "date_format": ("Dates standardized to YYYY-MM-DD", "توحيد صيغة التواريخ إلى YYYY-MM-DD", "format"),
    "excel_date": ("Excel serial numbers converted to dates", "تحويل أرقام إكسل إلى تواريخ", "format"),
    "hijri_date": ("Hijri dates converted to Gregorian", "تحويل التواريخ الهجرية إلى ميلادية", "format"),
    "money_format": ("Currency text removed from amounts (JD, د.ا)", "إزالة رموز العملة من المبالغ (JD، د.ا)", "format"),
    "decimal_comma": ("Decimal commas fixed (0,350 → 0.350)", "تصحيح الفاصلة العشرية (0,350 ← 0.350)", "format"),
    "fils_to_jd": ("Prices typed in fils converted to JD (350 → 0.350)", "تحويل الأسعار المكتوبة بالفلس إلى دينار (350 ← 0.350)", "fix"),
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
    "derived_total": ("Missing totals calculated (qty × price)", "حساب الإجمالي الناقص (الكمية × السعر)", "fill"),
    "recalc_total": ("Wrong totals recalculated (qty × price)", "إعادة حساب الإجماليات الخاطئة", "fix"),
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
    "missing_required": ("Missing required values", "قيم أساسية ناقصة"),
    "unknown_product": ("Products not in your catalog", "أصناف غير موجودة بقائمتك"),
}
PRIORITY = ["memory", "fils_to_jd", "recalc_total", "derived_total", "product_match", "person_match", "branch_map", "payment_map", "city_map",
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


class Matcher:
    def __init__(self, entries: list[dict], loose: bool = False):
        self.entries = entries
        self.loose = loose
        self.keys, self.owner, self.skel, self.knums = [], [], {}, []
        self.exact: dict[str, int] = {}
        for i, e in enumerate(entries):
            for k in e["keys"]:
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
        best = process.extractOne(k, ckeys, scorer=fuzz.partial_token_set_ratio)
        if best and best[1] >= (90 if self.loose else 95) and len(k) >= 4:
            return self.entries[self.owner[cands[best[2]]]]["name"], 0.7
        return None, 0


def cluster_values(values: Counter, kind: str = "product") -> dict[str, tuple[str, float]]:
    groups: list[dict] = []
    loose = kind in ("branch", "city", "area", "company")
    for raw, cnt in values.most_common():
        disp = clean_text(raw)
        if not disp:
            continue
        mk, sk, nm, ar = match_key(disp), skeleton(disp), nums(disp), is_arabic(disp)
        target = None
        for g in groups:
            if nm != g["nums"]:
                continue
            if mk == g["mk"]:
                target, conf = g, 1.0
                break
            if len(mk) > 4 and fuzz.ratio(mk, g["mk"]) >= (90 if loose else 93):
                target, conf = g, 0.9
                break
            if sk and sk == g["sk"] and ar != g["ar"] and len(sk.replace(" ", "")) >= (3 if loose else 4):
                target, conf = g, 0.8
                break
            if loose and min(len(mk), len(g["mk"])) >= 4 and fuzz.partial_token_set_ratio(mk, g["mk"]) >= 95:
                target, conf = g, 0.75
                break
        if target is None:
            groups.append({"mk": mk, "sk": sk, "nums": nm, "ar": ar, "canon": disp, "members": [(raw, 1.0, cnt)]})
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


def run(headers: list[str], rows: list[list], mapping: dict[str, str | None], ctx: Context | None = None, today: dt.date | None = None) -> dict:
    ctx = ctx or Context()
    today = today or dt.date.today()
    fields = {h: mapping.get(h) for h in headers}
    entity = detect_entity({f for f in fields.values() if f})
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
            dayfirst = P.column_dayfirst(vals)
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
                if d.date() > today + dt.timedelta(days=1):
                    flags.append(Flag(ri, h, vals[ri], "future_date"))
                record(ri, ci, P.fmt_date(d), rule)

        elif kind in ("money", "quantity"):
            parsed = []
            for ri in range(n):
                v, rule = P.parse_number(rows[ri][ci] if ci < len(rows[ri]) and isinstance(rows[ri][ci], (int, float)) else vals[ri])
                parsed.append((v, rule))
            good = [v for v, _ in parsed if v is not None and v > 0]
            med = statistics.median(good) if good else 0
            prod_col = next((col_idx[x] for x, ff in fields.items() if ff == "product"), None)
            per_prod = defaultdict(list)
            if kind == "money" and prod_col is not None:
                for ri, (v, _) in enumerate(parsed):
                    if v and v < 100:
                        per_prod[match_key(raw[ri][prod_col])].append(v)
            for ri, (v, rule) in enumerate(parsed):
                if ri in blank:
                    continue
                if v is None:
                    if rule == "invalid_number":
                        flags.append(Flag(ri, h, vals[ri], "invalid_number"))
                    elif rule == "null_token":
                        record(ri, ci, "", "null_token")
                    continue
                conf = 1.0
                if kind == "money" and v >= 50 and float(v).is_integer():
                    ref = per_prod.get(match_key(raw[ri][prod_col]) if prod_col is not None else "", [])
                    ref_med = statistics.median(ref) if ref else None
                    small = [x for x in good if x < 50]
                    if ref_med and ref_med < 50 and abs(v / 1000 - ref_med) <= max(0.6 * ref_med, 0.2):
                        v, rule, conf = v / 1000, "fils_to_jd", 0.92
                    elif not ref_med and small and len(small) >= 0.6 * len(good) and v >= 100 and v / 1000 <= max(small) * 1.5:
                        v, rule, conf = v / 1000, "fils_to_jd", 0.85
                if kind == "quantity":
                    if v < 0:
                        flags.append(Flag(ri, h, vals[ri], "negative_qty"))
                    elif med and v > max(50, med * 40):
                        flags.append(Flag(ri, h, vals[ri], "qty_outlier"))
                new = _fmt_num(v, kind == "money")
                if rule is None and new != vals[ri]:
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
                matcher = Matcher(ctx.branches, loose=True)
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

    qi = next((col_idx[x] for x, ff in fields.items() if ff == "quantity"), None)
    pi = next((col_idx[x] for x, ff in fields.items() if ff == "unit_price"), None)
    ti = next((col_idx[x] for x, ff in fields.items() if ff == "total"), None)
    if qi is not None and pi is not None and ti is not None:
        for ri in range(n):
            if ri in blank:
                continue
            try:
                q, p = float(clean[ri][qi]), float(clean[ri][pi])
            except ValueError:
                continue
            if q <= 0 or q > 200:
                continue
            exp = round(q * p, 3)
            if exp > 2000:
                continue
            t = clean[ri][ti]
            if not t:
                record(ri, ti, f"{exp:.3f}", "derived_total", 0.95)
            else:
                try:
                    tv = float(t)
                    if abs(tv - exp) > 0.011 and abs(tv - exp) > 0.02 * max(abs(exp), 0.001):
                        record(ri, ti, f"{exp:.3f}", "recalc_total", 0.85)
                except ValueError:
                    pass

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
        conf = 0.92 if rule == "fils_to_jd" else 0.85 if rule == "recalc_total" else 0.95 if rule == "derived_total" else 1.0
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
        for ri in range(n):
            if ri in blank or ri in dup:
                continue
            if not clean[ri][ci]:
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
        return v in ("cash", "card", "cliq", "wallet")
    if kind == "id":
        return v == v.strip() and not P.has_arabic_digits(v) and v == v.upper()
    return v == clean_text(v)


def score(headers, rows, fields, entity, today, cleaned: bool) -> dict:
    n = len(rows)
    if n == 0:
        return {"score": 0, "dimensions": {k: 0 for k in WEIGHTS}}
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

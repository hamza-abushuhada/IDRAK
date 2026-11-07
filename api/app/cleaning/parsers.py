import datetime as dt
import re

from .arabic import CITY_LOOKUP, PAYMENT_LOOKUP, clean_text, fold_arabic, is_null, match_key, to_western_digits

NUM_RE = re.compile(r"^-?\d+(\.\d+)?$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?$")
E164 = re.compile(r"^\+962\d{8,9}$")
EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
CURRENCY = re.compile(r"(jod|jd|j\.d|د\.ا|د\.أ|دينار|dinar|\$|usd|fils|فلس)", re.I)

AR_MONTHS = {
    "كانون الثاني": 1, "شباط": 2, "اذار": 3, "آذار": 3, "نيسان": 4, "ايار": 5, "أيار": 5, "حزيران": 6, "تموز": 7, "اب": 8, "آب": 8,
    "ايلول": 9, "أيلول": 9, "تشرين الاول": 10, "تشرين الأول": 10, "تشرين الثاني": 11, "كانون الاول": 12, "كانون الأول": 12,
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7, "اغسطس": 8, "أغسطس": 8,
    "سبتمبر": 9, "اكتوبر": 10, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}
EN_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
EMAIL_TYPOS = {"gmial.com": "gmail.com", "gmal.com": "gmail.com", "gmai.com": "gmail.com", "gamil.com": "gmail.com", "gmail.co": "gmail.com",
               "hotmial.com": "hotmail.com", "hotmal.com": "hotmail.com", "hotmail.co": "hotmail.com", "yaho.com": "yahoo.com",
               "yahooo.com": "yahoo.com", "outlok.com": "outlook.com", "outloo.com": "outlook.com", "icloud.co": "icloud.com"}


def has_arabic_digits(v) -> bool:
    return bool(re.search(r"[٠-٩۰-۹٫٬]", str(v)))


def parse_number(v):
    if v is None:
        return None, None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), None
    raw = str(v)
    s = clean_text(raw)
    if not s or is_null(s):
        return None, ("null_token" if s else None)
    rule = "arabic_digits" if has_arabic_digits(raw) else None
    s2 = CURRENCY.sub("", s).strip()
    if s2 != s:
        rule = rule or "money_format"
    s2 = re.sub(r"\b(pcs|pc|piece|pieces|حبة|حبات|قطعة|units?)\b", "", s2, flags=re.I).strip()
    if s2 != s and not rule:
        rule = "quantity_format"
    neg = s2.startswith("(") and s2.endswith(")")
    s2 = s2.strip("()").replace(" ", "")
    if "," in s2 and "." not in s2:
        if re.fullmatch(r"-?[1-9]\d{0,2}(,\d{3})+", s2):
            s2 = s2.replace(",", "")
        else:
            s2 = s2.replace(",", ".")
            rule = rule or "decimal_comma"
    elif "," in s2:
        s2 = s2.replace(",", "")
    if not NUM_RE.match(s2):
        return None, "invalid_number"
    val = float(s2) * (-1 if neg else 1)
    if rule is None and s2 != s:
        rule = "whitespace"
    return val, rule


def _excel(n: float):
    if 20000 <= n <= 60000:
        return dt.datetime(1899, 12, 30) + dt.timedelta(days=float(n))
    return None


def parse_date(v, dayfirst: bool = True):
    if v is None:
        return None, None
    if isinstance(v, dt.datetime):
        return v, None
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day), None
    if isinstance(v, (int, float)):
        d = _excel(v)
        return (d, "excel_date") if d else (None, "invalid_date")
    raw = str(v)
    s = clean_text(raw)
    if not s or is_null(s):
        return None, ("null_token" if s else None)
    rule = "arabic_digits" if has_arabic_digits(raw) else None
    s = re.sub(r"\s*(هـ|ه|م)\.?\s*$", "", s).strip()
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        d = _excel(float(s))
        return (d, "excel_date") if d else (None, "invalid_date")
    t = None
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm|ص|م)?", s, re.I)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        ap = (m.group(4) or "").lower()
        if ap in ("pm", "م") and hh < 12:
            hh += 12
        if ap in ("am", "ص") and hh == 12:
            hh = 0
        t = (hh % 24, mm)
        s = (s[: m.start()] + s[m.end():]).strip(" ,T")
    y = mo = d = None
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
        if m:
            a, b, c = map(int, m.groups())
            y = c + 2000 if c < 100 else c
            if a > 12:
                d, mo = a, b
            elif b > 12:
                mo, d = a, b
            else:
                d, mo = (a, b) if dayfirst else (b, a)
        else:
            low = fold_arabic(s.lower())
            for name, num in sorted(AR_MONTHS.items(), key=lambda x: -len(x[0])):
                if fold_arabic(name) in low:
                    nums = [int(x) for x in re.findall(r"\d+", low)]
                    if len(nums) >= 2:
                        d, y, mo = nums[0], nums[-1], num
                    break
            if y is None:
                m = re.search(r"([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", low) or None
                if m:
                    mo, d, y = EN_MONTHS.get(m.group(1)), int(m.group(2)), int(m.group(3))
                else:
                    m = re.search(r"(\d{1,2})\s+([a-z]{3})[a-z]*\.?,?\s+(\d{4})", low)
                    if m:
                        d, mo, y = int(m.group(1)), EN_MONTHS.get(m.group(2)), int(m.group(3))
    if not (y and mo and d):
        return None, "invalid_date"
    try:
        if 1300 <= y <= 1500:
            from hijridate import Hijri
            g = Hijri(y, mo, d).to_gregorian()
            out = dt.datetime(g.year, g.month, g.day)
            rule = "hijri_date"
        else:
            out = dt.datetime(y, mo, d)
    except (ValueError, OverflowError):
        return None, "invalid_date"
    if t:
        out = out.replace(hour=t[0], minute=t[1])
    if rule is None and not ISO_DATE.match(clean_text(raw)):
        rule = "date_format"
    return out, rule


def fmt_date(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M") if (d.hour or d.minute) else d.strftime("%Y-%m-%d")


def column_dayfirst(values) -> bool:
    first_gt, second_gt = 0, 0
    for v in values:
        s = to_western_digits(str(v or ""))
        m = re.match(r"^\s*(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            first_gt += a > 12
            second_gt += b > 12
    return not (second_gt > first_gt)


def parse_phone(v):
    if v is None:
        return None, None
    raw = str(v)
    s = clean_text(raw)
    if not s or is_null(s):
        return None, ("null_token" if s else None)
    digits = re.sub(r"\D", "", s)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("962"):
        digits = digits[3:]
    digits = digits.lstrip("0")
    if re.fullmatch(r"7[789]\d{7}", digits) or re.fullmatch(r"[2-6]\d{7}", digits):
        out = "+962" + digits
        return out, (None if s == out else ("arabic_digits" if has_arabic_digits(raw) and False else "phone_e164"))
    return None, "invalid_phone"


def parse_email(v):
    if v is None:
        return None, None
    s = clean_text(v).lower().replace(" ", "")
    if not s or is_null(s):
        return None, ("null_token" if s else None)
    user, _, dom = s.partition("@")
    rule = None
    if dom in EMAIL_TYPOS:
        dom = EMAIL_TYPOS[dom]
        rule = "email_fix"
    out = f"{user}@{dom}"
    if not EMAIL.match(out):
        return None, "invalid_email"
    if rule is None and out != str(v):
        rule = "whitespace"
    return out, rule


def map_payment(v):
    s = clean_text(v)
    if not s or is_null(s):
        return None, ("null_token" if s else None)
    k = match_key(s)
    if k in PAYMENT_LOOKUP:
        out = PAYMENT_LOOKUP[k]
        return out, (None if s == out else "payment_map")
    for key, val in PAYMENT_LOOKUP.items():
        if key and key in k:
            return val, "payment_map"
    return None, "unknown_payment"


def map_city(v):
    s = clean_text(v)
    if not s or is_null(s):
        return None, ("null_token" if s else None)
    k = match_key(s)
    if k in CITY_LOOKUP:
        out = CITY_LOOKUP[k]
        return out, (None if s == out else "city_map")
    for key, val in CITY_LOOKUP.items():
        if len(key) >= 3 and key in k:
            return val, "city_map"
    from rapidfuzz import fuzz, process
    best = process.extractOne(k, list(CITY_LOOKUP), scorer=fuzz.ratio)
    if best and best[1] >= 85:
        return CITY_LOOKUP[best[0]], "city_map"
    return s, None

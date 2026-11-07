import re
import unicodedata

ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
INVISIBLE = dict.fromkeys(map(ord, "​‌‍‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"), None)
DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
TATWEEL = "ـ"
ARABIC_CHARS = re.compile(r"[؀-ۿ]")
NULL_TOKENS = {"", "-", "--", "—", "n/a", "na", "null", "none", "nil", "nan", "?", "؟", "لا يوجد", "غير معروف",
               "unknown", "#n/a", "#value!", "0000-00-00", "x"}

UNIT_MAP = [
    (r"\b(مل|ملل|مللي|ملي)\b", "ml"), (r"\b(لتر|ليتر|لترات)\b", "l"), (r"\b(غم|غرام|جرام|جم|غ)\b", "g"),
    (r"\b(كغ|كيلو|كيلوغرام|كجم|kg|kgs|kilo)\b", "kg"), (r"\b(حبه|حبة|قطعه|قطعة|pcs|pc|piece|pieces)\b", "pc"),
    (r"\b(علبه|علبة|can|cans|tin)\b", "can"), (r"\b(كرتونه|كرتونة|carton|ctn)\b", "ctn"),
    (r"\b(ltr|litre|liter|lt)\b", "l"), (r"\b(gm|gr|gram|grams)\b", "g"), (r"\b(mls|milliliter)\b", "ml"),
]


def is_arabic(s: str) -> bool:
    return bool(ARABIC_CHARS.search(s or ""))


def to_western_digits(s: str) -> str:
    return s.translate(ARABIC_INDIC).replace("٫", ".").replace("٬", ",")


def clean_text(v) -> str:
    if v is None:
        return ""
    s = str(v)
    s = unicodedata.normalize("NFKC", s).translate(INVISIBLE)
    s = to_western_digits(s).replace(TATWEEL, "")
    s = DIACRITICS.sub("", s)
    s = s.replace(" ", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_null(v) -> bool:
    return clean_text(v).lower() in NULL_TOKENS


def fold_arabic(s: str) -> str:
    s = re.sub("[إأآٱ]", "ا", s)
    s = s.replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي").replace("ء", "")
    return s


def match_key(v) -> str:
    s = fold_arabic(clean_text(v).lower())
    s = re.sub(r"(\d)\s*(ml|l|g|kg|مل|لتر|غم|كغ)", r"\1 \2", s)
    for pat, rep in UNIT_MAP:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\b(ال)(?=\w{3,})", "", s)
    return re.sub(r"\s+", " ", s).strip()


_AR2LAT = {
    "ب": "b", "ت": "t", "ث": "t", "ج": "j", "ح": "h", "خ": "k", "د": "d", "ذ": "d", "ر": "r", "ز": "z",
    "س": "s", "ش": "s", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "", "غ": "g", "ف": "f", "ق": "k",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "", "ي": "", "ا": "", "ة": "", "ى": "", "ء": "",
}
_LAT = str.maketrans({"p": "b", "v": "f", "q": "k", "c": "k", "x": "k", "w": "", "y": "", "e": "", "i": "", "o": "", "u": "", "a": ""})


def nums(v) -> list[str]:
    return sorted(re.findall(r"\d+(?:\.\d+)?", clean_text(v)))


def skeleton(v) -> str:
    s = fold_arabic(clean_text(v).lower())
    s = re.sub(r"\b(al|el)[-\s]", "", s)
    s = re.sub(r"(^|\s)ال(?=\S{3,})", r"\1", s)
    out = []
    for ch in s:
        if ch in _AR2LAT:
            out.append(_AR2LAT[ch])
        elif ch.isascii() and ch.isalpha():
            out.append(ch.translate(_LAT))
        elif ch.isdigit():
            out.append(ch)
        elif ch.isspace():
            out.append(" ")
    s = "".join(out)
    s = s.replace("sh", "s").replace("ch", "s").replace("ph", "f").replace("th", "t").replace("kh", "k").replace("gh", "g")
    s = re.sub(r"(.)\1+", r"\1", s)
    words = [re.sub(r"(?<=\w)h$", "", w) for w in s.split() if w]
    return " ".join(w for w in words if w)


UNIT_WORDS = {"ml", "l", "g", "kg", "pcs", "pc", "x", "can", "ltr", "gm"}


def smart_title(s: str) -> str:
    all_upper = s.isupper()

    def fix(w: str) -> str:
        lw = w.lower()
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(ml|l|g|kg|pc|pcs|x\d+)?", lw)
        if m:
            unit = m.group(2) or ""
            return m.group(1) + ("L" if unit == "l" else unit)
        if lw in UNIT_WORDS:
            return "L" if lw == "l" else lw
        if is_arabic(w):
            return w
        if "-" in w:
            return "-".join(fix(p) for p in w.split("-"))
        if not w.isalpha():
            return w
        if len(w) <= 3 and w.isupper() and not all_upper:
            return w
        return w[:1].upper() + w[1:].lower()
    return " ".join(fix(w) for w in s.split(" "))


JORDAN_CITIES = {
    "Amman": ["amman", "عمان", "عمّان", "amman city", "3amman", "omman"],
    "Irbid": ["irbid", "اربد", "إربد", "irbed", "erbid"],
    "Zarqa": ["zarqa", "الزرقاء", "زرقاء", "zarka", "al zarqa"],
    "Aqaba": ["aqaba", "العقبة", "العقبه", "akaba"],
    "Salt": ["salt", "السلط", "as-salt", "al salt"],
    "Madaba": ["madaba", "مادبا", "maadaba"],
    "Jerash": ["jerash", "جرش", "jarash"],
    "Karak": ["karak", "الكرك", "kerak", "al karak"],
    "Mafraq": ["mafraq", "المفرق", "mafrak"],
    "Ajloun": ["ajloun", "عجلون", "ajlun"],
    "Ma'an": ["maan", "ma'an", "معان"],
    "Tafilah": ["tafilah", "الطفيلة", "tafila"],
}
CITY_LOOKUP = {match_key(v): k for k, vs in JORDAN_CITIES.items() for v in vs + [k]}

PAYMENT_METHODS = {
    "cash": ["cash", "كاش", "نقدي", "نقدا", "نقداً", "نقد", "cash payment"],
    "card": ["card", "visa", "فيزا", "بطاقة", "بطاقه", "mastercard", "master card", "credit card", "debit", "pos", "ماستر كارد"],
    "cliq": ["cliq", "كليك", "click", "cliq transfer", "تحويل كليك"],
    "wallet": ["wallet", "محفظة", "محفظه", "zain cash", "زين كاش", "orange money", "اورانج موني", "e-wallet", "dinarak", "دينارك"],
}
PAYMENT_LOOKUP = {match_key(v): k for k, vs in PAYMENT_METHODS.items() for v in vs}

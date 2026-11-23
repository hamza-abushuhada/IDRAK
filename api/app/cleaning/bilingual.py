"""The same menu item written in English and in Arabic.

POS exports mix languages: "Crispy Zinger Sandwich" and "ساندويش زنجر دجاج مقرمش"
are one product, sold at one price, but became two products that split the item's
sales. Spelling matchers can't see it (no letters in common), so an English name
is paired with an Arabic one only when all of these hold:

  * the words agree: each English word is either translated by GLOSSARY or
    sounds like an Arabic word (skeleton: zinger ~ زنجر, fattoush ~ فتوش),
    for at least 60% of the English name and two words (one for one-word names);
  * the price is the same (within 2%), and both prices are known;
  * the category, when both rows have one, is the same;
  * sizes don't contradict (330ml is not 1 لتر; 500ml is 0.5 لتر);
  * exactly one Arabic name is the best fit.

Every pairing is a "product_match" change the user reviews; nothing merges silently.
"""
from __future__ import annotations

import re

from .arabic import UNIT_MAP, clean_text, is_arabic, match_key, skeleton

# English word -> Arabic words it translates to (match_key forms). Transliterated
# names (shawarma, zinger, kebab, hummus...) need no entry: skeleton() matches them.
GLOSSARY = {
    "chicken": ["دجاج", "دجاجه", "فروج"], "beef": ["لحم", "لحمه"], "meat": ["لحم", "لحمه"],
    "lamb": ["خاروف", "غنم"], "sandwich": ["ساندويش", "ساندويتش", "سندويش", "سندويشه"], "meal": ["وجبه"],
    "family": ["عايلي"], "salad": ["سلطه"], "caesar": ["سيزر"], "grilled": ["مشوي", "مشويه", "فحم"],
    "grill": ["مشاوي", "مشوي", "مشويه"], "mixed": ["مشكل", "مشكله"], "crispy": ["مقرمش", "مقرمشه"],
    "juice": ["عصير"], "orange": ["برتقال"], "fresh": ["طازج", "طازجه", "طبيعي"], "water": ["ماء", "مياه", "مي"],
    "mineral": ["معدني", "معدنيه"], "cheese": ["جبنه", "تشيز"], "cheeseburger": ["تشيز", "برجر"],
    "rice": ["ارز", "رز"], "half": ["نصف", "نص"], "whole": ["كامل", "كامله"], "roasted": ["شوايه", "مشوي", "محمر"],
    "plate": ["صحن"], "pine": ["صنوبر"], "nuts": ["مكسرات", "صنوبر"], "eggplant": ["باذنجان"],
    "aleppo": ["حلبي"], "fries": ["بطاطا", "مقليه"], "potato": ["بطاطا"], "om": ["ام"], "umm": ["ام"],
    "cream": ["قشطه", "كريمه"], "fajita": ["فاهيتا"], "arabic": ["عربي"], "mexican": ["مكسيكي"],
    "pomegranate": ["رمان"], "local": ["بلدي"], "7up": ["سفن"], "seven": ["سفن"], "coca": ["كوكا"],
    "cola": ["كولا"], "garlic": ["ثوم"], "bread": ["خبز"], "soup": ["شوربه"], "lentil": ["عدس"],
    "tea": ["شاي"], "coffee": ["قهوه"], "lemon": ["ليمون"], "mint": ["نعنع"], "yogurt": ["لبن"],
    "falafel": ["فلافل"], "pieces": ["قطع"], "pcs": ["قطع"],
}
GLOSSARY = {en: [match_key(a) for a in ars] for en, ars in GLOSSARY.items()}  # "ماء" is "ما" once normalized
# Words that carry no identity in either language.
STOP = {"with", "and", "the", "a", "of", "in", "on", "special", "style", "can", "ml", "l", "g", "kg", "pc", "x",
        "french", "مع", "و"}
_QTY = re.compile(r"^\d+(\.\d+)?(ml|l|g|kg|pc|pcs|x)?$")
_PREFIXES = ("بال", "وال", "لل", "ال", "عال", "ب", "و", "ع")


def _skel(word: str) -> str:
    return skeleton(word).replace("j", "g").replace(" ", "")


def _en_words(name: str) -> list[str]:
    return [w for w in match_key(name).split() if w not in STOP and not _QTY.match(w)]


def _ar_forms(name: str) -> tuple[set[str], set[str]]:
    """(Arabic words with and without clitics, their sound skeletons)."""
    words = set()
    for w in match_key(name).split():
        if w in STOP or _QTY.match(w):
            continue
        words.add(w)
        for p in _PREFIXES:
            if w.startswith(p) and len(w) - len(p) >= 3:
                words.add(w[len(p):])
    return words, {s for w in words if len(s := _skel(w)) >= 2}


def _litres(name: str) -> set[float]:
    """Sizes in a common unit: 500ml and 0.5 لتر are both 0.5.

    Read from the text itself: match_key drops the decimal point ("0.5" -> "0 5").
    """
    s = clean_text(name).lower()
    for pat, rep in UNIT_MAP:
        s = re.sub(pat, rep, s)
    s = s.replace(" ", "")
    out = set()
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)(ml|l|g|kg)?", s):
        v = float(num)
        out.add(round(v / 1000, 3) if unit in ("ml", "g") else round(v, 3))
    return out


def score(en: str, ar: str) -> float:
    """Share of the English name's words found in the Arabic name (0 when sizes clash)."""
    ew = _en_words(en)
    if not ew:
        return 0.0
    sa, sb = _litres(en), _litres(ar)
    if sa and sb and not (sa & sb):
        return 0.0
    aw, askel = _ar_forms(ar)
    hit = 0
    for w in ew:
        if any(t in aw for t in GLOSSARY.get(w, ())) or (len(sk := _skel(w)) >= 2 and sk in askel):
            hit += 1
    if hit < min(2, len(ew)):
        return 0.0
    return hit / len(ew)


def _same_price(a: float | None, b: float | None) -> bool:
    return bool(a and b and abs(a - b) <= 0.02 * max(a, b))


def pair(english: dict[str, tuple[float | None, str | None]],
         arabic: dict[str, tuple[float | None, str | None]], threshold: float = 0.6) -> dict[str, tuple[str, float]]:
    """{english name: (arabic name, score)} for the pairs that pass every check above.

    english / arabic: name -> (unit price, category or None).
    """
    out = {}
    for en, (ep, ec) in english.items():
        if is_arabic(en) or not clean_text(en):
            continue
        ranked = []
        for ar, (ap, ac) in arabic.items():
            if not _same_price(ep, ap) or (ec and ac and match_key(ec) != match_key(ac)):
                continue
            s = score(en, ar)
            if s >= threshold:
                ranked.append((s, ar))
        ranked.sort(reverse=True)
        if ranked and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
            out[en] = (ranked[0][1], round(ranked[0][0], 2))
    return out

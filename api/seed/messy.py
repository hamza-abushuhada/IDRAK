import csv
import re
import datetime as dt
import random
import shutil
from pathlib import Path

import asyncpg
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from app.config import settings

R = random.Random(7)
OUT = Path(__file__).parent / "out"
WEB_SAMPLES = Path(__file__).resolve().parents[2] / "web" / "public" / "samples"
AI = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
AR_MONTHS = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول"]


def ar_digits(s):
    return str(s).translate(AI)


def messy_date(d: dt.datetime):
    k = R.random()
    if k < 0.22:
        return d.strftime("%Y-%m-%d")
    if k < 0.40:
        return d.strftime("%d/%m/%Y")
    if k < 0.50:
        return f"{d.day}-{d.month}-{d.strftime('%y')}"
    if k < 0.58:
        return d.strftime("%b %d, %Y")
    if k < 0.68:
        return ar_digits(d.strftime("%d/%m/%Y"))
    if k < 0.74:
        return f"{d.day} {AR_MONTHS[d.month - 1]} {d.year}"
    if k < 0.82:
        return (d.date() - dt.date(1899, 12, 30)).days
    if k < 0.90:
        return d.strftime("%Y/%m/%d %H:%M")
    if k < 0.93:
        from hijridate import Gregorian
        h = Gregorian(d.year, d.month, d.day).to_hijri()
        return f"{h.year}/{h.month:02d}/{h.day:02d} هـ"
    if k < 0.96:
        return ""
    return d.strftime("%m/%d/%Y") if d.day > 12 else d.strftime("%d.%m.%Y")


def messy_name(en, ar):
    k = R.random()
    if k < 0.30:
        s = ar
    elif k < 0.55:
        s = en
    elif k < 0.65:
        s = en.upper()
    elif k < 0.72:
        s = en.lower() + "  "
    elif k < 0.80:
        s = ar.replace("أ", "ا").replace("ة", "ه").replace("ي ", "ى ").replace("إ", "ا")
    elif k < 0.86:
        s = ar_digits(ar)
    elif k < 0.90:
        s = ar.replace("ي", "يـ", 1)
    elif k < 0.95:
        s = re.sub(r"(\d)L", r" ltr", en.replace(" ", "  ", 1).replace("ml", " ML"))
    else:
        s = list(en)
        if len(s) > 5:
            i = R.randint(1, len(s) - 3)
            s[i], s[i + 1] = s[i + 1], s[i]
        s = "".join(s)
    return s


SPECIAL_NAMES = {
    "Pepsi 330ml can": ["Pepsi can", "PEPSI 330ML", "ببسي ٣٣٠", "بيبسي 330", "pepsi 330 ml", "بيبسي علبه"],
    "Ghadeer Water 600ml": ["مياه غدير صغير", "Ghadeer 600", "غدير ٦٠٠ مل", "ghadeer water small"],
    "Arabic Bread (Kmaj) pack": ["خبز", "كماج", "Bread kmaj", "خبز كماج ربطه", "ARABIC BREAD"],
    "Hammoudeh Fresh Milk 1L": ["حليب حموده ١ لتر", "Hammoudeh milk 1L", "حليب حمودة", "HAMMOUDEH FRESH MILK 1 LTR"],
    "Al Ameed Coffee with Cardamom 200g": ["قهوة العميد", "قهوه العميد هيل ٢٠٠", "Al-Ameed coffee 200g", "AMEED COFFEE"],
}


def messy_price(p):
    k = R.random()
    if k < 0.40:
        return f"{p:.3f}"
    if k < 0.52:
        return ar_digits(f"{p:.3f}").replace(".", "٫")
    if k < 0.62:
        return str(int(round(p * 1000)))
    if k < 0.72:
        return f"{p:.2f} JD"
    if k < 0.80:
        return f"د.ا {p:.3f}"
    if k < 0.86:
        return f"{p:.3f}".replace(".", ",")
    if k < 0.92:
        return p
    return ""


def messy_qty(q):
    k = R.random()
    if k < 0.62:
        return q
    if k < 0.78:
        return ar_digits(q)
    if k < 0.86:
        return f"{q}.0"
    if k < 0.90:
        return -q
    if k < 0.94:
        return ""
    return f"{q} pcs"


def messy_phone(ph):
    if not ph:
        return ""
    n = ph.replace("+962", "")
    k = R.random()
    forms = [f"0{n}", f"+962 {n[:2]} {n[2:5]} {n[5:]}", f"00962{n}", f"{n[:2]}-{n[2:5]}-{n[5:]}", ar_digits(f"0{n}"), f"962{n}", f"0{n[:5]}", ""]
    w = [0.3, 0.14, 0.1, 0.1, 0.12, 0.08, 0.06, 0.1]
    return R.choices(forms, w)[0]


BRANCH = ["Khalda", "خلدا", "KHALDA ", "فرع خلدا", "khalda branch", "خلدة", "Khalda"]
PAY = ["cash", "كاش", "CASH", "نقدي", "Visa", "فيزا", "بطاقة", "card", "CliQ", "كليك", "زين كاش", "Cash ", "n/a"]
CITY = ["Amman", "عمان", "عمّان", "AMMAN", "amman ", "Amman", "عمان الغربية", ""]


async def write_messy_files():
    OUT.mkdir(exist_ok=True)
    WEB_SAMPLES.mkdir(parents=True, exist_ok=True)
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)
    try:
        org = await conn.fetchval("select id from organizations where slug='al-nashama'")
        prods = await conn.fetch("select name, name_ar, price from products where org_id=$1 and is_active", org)
        weights = [5 if p["name"] in SPECIAL_NAMES else 1 for p in prods]
        cashiers = await conn.fetch("""select e.full_name, e.full_name_ar from employees e join branches b on b.id=e.branch_id
                                       where e.org_id=$1 and b.name='Khalda' and e.job_title in ('cashier','supervisor')""", org)
        custs = await conn.fetch("select phone from customers where org_id=$1 limit 120", org)
    finally:
        await conn.close()

    rows = []
    day = dt.datetime.now().replace(hour=8, minute=0, second=0, microsecond=0) - dt.timedelta(days=1)
    inv = 88000
    while len(rows) < 620:
        inv += 1
        t = day + dt.timedelta(minutes=R.randint(0, 15 * 60))
        cashier = R.choice(cashiers)
        cname = R.choice([cashier["full_name"], cashier["full_name_ar"], cashier["full_name"].upper(), cashier["full_name"].split(" ")[0]])
        pay = R.choice(PAY)
        phone = messy_phone(R.choice(custs)["phone"]) if R.random() < 0.55 else ""
        date_v = messy_date(t)
        branch = R.choice(BRANCH)
        city = R.choice(CITY)
        inv_v = R.choice([f"KH-POS-{inv}", f"KH-POS-{inv}", ar_digits(f"KH-POS-{inv}"), f"kh-pos-{inv} "])
        for _ in range(R.randint(1, 4)):
            p = R.choices(prods, weights)[0]
            name = R.choice(SPECIAL_NAMES[p["name"]]) if p["name"] in SPECIAL_NAMES and R.random() < 0.7 else messy_name(p["name"], p["name_ar"])
            q = R.choice([1, 1, 1, 2, 2, 3, 6])
            price = float(p["price"])
            qv, pv = messy_qty(q), messy_price(price)
            tot = round(q * price, 3)
            tv = R.choice([f"{tot:.3f}", f"{tot:.3f}", ar_digits(f"{tot:.3f}"), "", f"{tot:.3f} JD", f"{tot * 1.2:.3f}"])
            rows.append([inv_v, date_v, branch, cname, name, qv, pv, tv, pay, phone, city])
    for _ in range(34):
        i = R.randint(0, len(rows) - 1)
        rows.insert(i + 1, list(rows[i]))
    for _ in range(6):
        rows.insert(R.randint(0, len(rows) - 1), [""] * 11)
    for _ in range(4):
        i = R.randint(0, len(rows) - 1)
        rows[i][5] = R.choice([500, 999, 1200])

    headers = ["رقم الفاتورة ", "Date", "الفرع", "Cashier", "اسم الصنف", "Qty", "سعر الوحدة", "الإجمالي", "طريقة الدفع", "Customer Phone", "City"]
    wb = Workbook()
    ws = wb.active
    ws.title = "POS Export"
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="EFE6D8")
    for r in rows:
        ws.append(r)
    ws.column_dimensions["E"].width = 34
    p1 = OUT / "pos_export_messy.xlsx"
    wb.save(p1)
    shutil.copy(p1, WEB_SAMPLES / p1.name)

    with open(OUT / "customers_from_whatsapp.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["الاسم", "رقم الموبايل", "المنطقة", "City", "email", "ملاحظات"])
        from seed.catalog import FAMILY, FEMALE, MALE, AREAS
        for i in range(260):
            first = R.choice(MALE + FEMALE)
            fam = R.choice(FAMILY)
            nm = R.choice([f"{first[1]} {fam[1]}", f"{first[0]} {fam[0]}", f"{first[0].lower()} {fam[0].lower()}", f"ابو {R.choice(MALE)[1]}", f"ام {R.choice(MALE)[1]}", f"{first[1]}"])
            ph = messy_phone(f"+9627{R.choice('789')}{R.randint(1000000, 9999999)}")
            area = R.choice(AREAS["Amman"])
            em = R.choice(["", "", f"{first[0].lower()}{R.randint(1, 99)}@gmial.com", f"{first[0].lower()}.{fam[0].lower().replace('al-', '')}@example.com", "N/A"])
            w.writerow([nm, ph, R.choice([area[1], area[0], area[0].upper(), ""]), R.choice(CITY), em, R.choice(["", "زبون دائم", "VIP", "بدو توصيل", ""])])
            if R.random() < 0.08:
                w.writerow([nm.upper() if nm.isascii() else nm, ph, area[1], "عمان", em, ""])
    shutil.copy(OUT / "customers_from_whatsapp.csv", WEB_SAMPLES / "customers_from_whatsapp.csv")

    with open(OUT / "supplier_prices.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["المورد", "الصنف", "سعر الكرتونة", "عدد الحبات بالكرتونة", "سعر الحبة", "تاريخ آخر تحديث"])
        for p in R.sample(list(prods), 90):
            per = R.choice([6, 12, 24])
            cost = float(p["price"]) * 0.74
            w.writerow([R.choice(["الوفاء للتجارة", "Al-Wafa Trading", "الوفاء", "AL WAFA TRADING & IMPORT"]), messy_name(p["name"], p["name_ar"]),
                        messy_price(cost * per), ar_digits(per) if R.random() < 0.3 else per, messy_price(cost),
                        messy_date(dt.datetime.now() - dt.timedelta(days=R.randint(1, 200)))])
    shutil.copy(OUT / "supplier_prices.csv", WEB_SAMPLES / "supplier_prices.csv")
    print(f"  messy files written to {OUT} and web/public/samples ({len(rows)} POS rows)")

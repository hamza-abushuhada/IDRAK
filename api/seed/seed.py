import asyncio
import datetime as dt
import math
import os
import random
import sys
import uuid
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
import httpx

from app.config import settings
from seed import catalog as C

RNG = random.Random(20261107)
AMMAN = dt.timezone(dt.timedelta(hours=3))
END = dt.date.today() - dt.timedelta(days=1)

DEMO_PASSWORD = "Idrak@Demo2026"
DEMO_USERS = [
    ("founder@idrak.example.com", "Hamza Abushuhada", "حمزة أبو شحادة", False),
    ("owner@nashama.example.com", "Khaled Al-Majali", "خالد المجالي", False),
    ("manager@nashama.example.com", "Rania Haddad", "رانيا حداد", False),
    ("accountant@nashama.example.com", "Mahmoud Obeidat", "محمود عبيدات", False),
    ("cashier@nashama.example.com", "Yazan Al-Zoubi", "يزن الزعبي", False),
    ("owner@alshifa.example.com", "Dr. Lina Al-Momani", "د. لينا المومني", False),
]

RAMADAN = [(dt.date(2025, 3, 1), dt.date(2025, 3, 29)), (dt.date(2026, 2, 18), dt.date(2026, 3, 19))]
EID_FITR = [dt.date(2025, 3, 30), dt.date(2026, 3, 20)]
EID_ADHA = [dt.date(2025, 6, 6), dt.date(2026, 5, 27)]


def uid() -> uuid.UUID:
    return uuid.UUID(int=RNG.getrandbits(128), version=4)


def r3(x: float) -> float:
    return round(x + 1e-9, 3)


def in_ramadan(d):
    for a, b in RAMADAN:
        if a <= d <= b:
            return (d - a).days, (b - d).days
    return None


def near(d, days_list, before=4, after=2):
    return any(-before <= (d - x).days <= after for x in days_list)


def is_summer(d):
    return d.month in (6, 7, 8, 9)


def is_winter(d):
    return d.month in (12, 1, 2)


def back_to_school(d):
    return (d.month == 8 and d.day >= 18) or (d.month == 9 and d.day <= 12)


async def ensure_users() -> dict[str, str]:
    base = settings.supabase_url + "/auth/v1/admin/users"
    h = {"apikey": settings.supabase_service_key, "Authorization": f"Bearer {settings.supabase_service_key}"}
    out = {}
    async with httpx.AsyncClient(timeout=30) as cx:
        existing = {}
        page = 1
        while True:
            r = await cx.get(base, headers=h, params={"page": page, "per_page": 200})
            r.raise_for_status()
            us = r.json().get("users", [])
            existing.update({u["email"]: u["id"] for u in us})
            if len(us) < 200:
                break
            page += 1
        for email, name, name_ar, _ in DEMO_USERS:
            meta = {"full_name": name, "full_name_ar": name_ar, "locale": "ar"}
            if email in existing:
                r = await cx.put(f"{base}/{existing[email]}", headers=h,
                                 json={"password": DEMO_PASSWORD, "email_confirm": True, "user_metadata": meta})
                r.raise_for_status()
                out[email] = existing[email]
            else:
                r = await cx.post(base, headers=h, json={"email": email, "password": DEMO_PASSWORD, "email_confirm": True, "user_metadata": meta})
                r.raise_for_status()
                out[email] = r.json()["id"]
    return out


def person(gender=None):
    g = gender or RNG.choice("MF")
    first = RNG.choice(C.MALE if g == "M" else C.FEMALE)
    fam = RNG.choice(C.FAMILY)
    return g, f"{first[0]} {fam[0]}", f"{first[1]} {fam[1]}"


def jo_mobile():
    return f"+9627{RNG.choice('789')}{RNG.randint(1000000, 9999999)}"


def build_products(spec, cats):
    prods = []
    for cat, brand, name, name_ar, sizes, pop, shelf, sup in spec:
        for i, (size, size_ar, cost, price) in enumerate(sizes):
            pid = uid()
            prods.append(dict(
                id=pid, cat=cat, category_id=cats[cat]["id"], tax=cats[cat]["tax"], supplier_key=sup, brand=brand,
                name=f"{name} {size}", name_ar=f"{name_ar} {size_ar}", base=name, size=size,
                cost=cost, price=price, pop=pop * (1.0 if i == 0 else 0.55 / i), shelf=shelf,
                perishable=bool(shelf and shelf <= 30), sku=f"{cat[:3].upper()}-{len(prods) + 1001}",
                barcode=f"62{RNG.randint(10**10, 10**11 - 1)}", dead=pop < 0.2,
            ))
    return prods


def minimarket_mult(p, d):
    cat, base, m = p["cat"], p["base"], 1.0
    rm = in_ramadan(d)
    pre_eid = rm is not None and rm[1] <= 6
    pre_adha = near(d, EID_ADHA, before=4, after=-1)
    if cat == "seasonal":
        if rm is not None:
            m *= {"Qatayef Dough": 25, "Vimto Cordial": 9, "Jallab Syrup": 9, "Tamarind Drink": 9, "Qamar Al-Din Apricot Paste": 10,
                  "Ma'amoul with Dates": 3}.get(base, 6)
        if base == "Ma'amoul with Dates" and (pre_eid or pre_adha):
            m *= 6
        if base == "Tang Orange" and is_summer(d):
            m *= 1.6
    elif cat == "sweets":
        if pre_eid or pre_adha:
            m *= 2.6
        if base in ("Mackintosh Quality Street", "Ferrero Rocher") and (pre_eid or pre_adha or d.month == 12):
            m *= 3
    elif cat == "beverages":
        m *= 1.5 if is_summer(d) else 0.8 if is_winter(d) else 1
        if rm is not None and "Juice" in base:
            m *= 1.9
    elif cat == "water":
        m *= 1.9 if is_summer(d) else 0.75 if is_winter(d) else 1
    elif cat == "chilled" and "Ice Cream" in base:
        m *= 3.2 if is_summer(d) else 0.25 if is_winter(d) else 0.9
    elif cat == "coffee_tea":
        if base == "Sahlab Powder":
            m *= 3.5 if is_winter(d) else 0.2 if is_summer(d) else 1
        else:
            m *= 1.3 if is_winter(d) else 0.9 if is_summer(d) else 1
    elif cat == "staples":
        m *= 1.45 if rm is not None else 1
        if d.day <= 5:
            m *= 1.25
    elif cat == "dairy":
        if rm is not None:
            m *= 1.6 if "Laban" in base else 1.3
    elif cat == "snacks":
        m *= 1.45 if back_to_school(d) else 1
    elif cat == "household":
        if base in ("Pilot Blue Pen", "School Notebook 100 sheets"):
            m *= 7 if back_to_school(d) else 0.5
        if base == "Charcoal for Arguileh":
            m *= 1.7 if is_summer(d) else 0.8
        if base == "Gas Cylinder Refill Voucher":
            m *= 3.2 if is_winter(d) else 0.3 if is_summer(d) else 1
    if p["dead"] and (END - d).days < 150:
        m *= 0.03
    return m


def pharmacy_mult(p, d):
    base, m = p["base"], 1.0
    if base in ("Panadol Cold & Flu", "Otrivin Nasal Spray", "Strepsils Honey Lemon", "Redoxon Vitamin C 1000mg"):
        m *= 2.8 if is_winter(d) or d.month in (11, 3) else 0.6
    if "Sun" in base:
        m *= 3.5 if is_summer(d) else 0.3
    if p["cat"] == "vitamins" and is_winter(d):
        m *= 1.4
    return m


HOURS_NORMAL = {7: 2, 8: 4, 9: 5, 10: 5, 11: 5, 12: 6, 13: 7, 14: 6, 15: 5, 16: 5, 17: 6, 18: 8, 19: 9, 20: 9, 21: 8, 22: 6, 23: 3, 0: 1}
HOURS_FRIDAY = {8: 2, 9: 3, 10: 4, 11: 3, 12: 2, 13: 6, 14: 9, 15: 8, 16: 7, 17: 7, 18: 8, 19: 9, 20: 9, 21: 8, 22: 6, 23: 4, 0: 2}
HOURS_RAMADAN = {9: 2, 10: 3, 11: 3, 12: 4, 13: 5, 14: 6, 15: 8, 16: 10, 17: 12, 18: 3, 19: 3, 20: 6, 21: 9, 22: 10, 23: 9, 0: 7, 1: 4}
HOURS_PHARMA = {9: 4, 10: 6, 11: 6, 12: 5, 13: 5, 14: 4, 15: 4, 16: 5, 17: 6, 18: 8, 19: 9, 20: 8, 21: 6, 22: 4, 23: 2}
WEEKDAY = {0: .92, 1: .93, 2: .97, 3: 1.15, 4: 1.2, 5: 1.05, 6: .95}


def simulate(org_id, branches, prods, employees, customers, start, end, mult_fn, items_mean, pharmacy=False, planted=None):
    planted = planted or {}
    sales, items = [], []
    sold = defaultdict(float)
    seq = {b["id"]: 0 for b in branches}
    cust_ids = [c["id"] for c in customers]
    cust_w = [c["w"] for c in customers]
    churned = planted.get("churned", set())
    churn_date = END - dt.timedelta(days=52)
    below_cost = planted.get("below_cost", {})
    bad_cashier = planted.get("bad_cashier")
    bad_since = END - dt.timedelta(days=150)
    total_days = (end - start).days + 1
    d = start
    while d <= end:
        rm = in_ramadan(d)
        weights = [max(1e-6, p["pop"] * mult_fn(p, d)) for p in prods]
        cum, acc = [], 0.0
        for w in weights:
            acc += w
            cum.append(acc)
        if pharmacy:
            hours = HOURS_PHARMA
        else:
            hours = HOURS_RAMADAN if rm is not None else HOURS_FRIDAY if d.weekday() == 4 else HOURS_NORMAL
        hk, hw = list(hours), list(hours.values())
        progress = (d - start).days / max(1, total_days)
        day_f = WEEKDAY[d.weekday()] * (1 + 0.11 * progress)
        if rm is not None:
            day_f *= 1.12 * (1.4 if rm[1] <= 3 else 1)
        if any(x <= d <= x + dt.timedelta(days=2) for x in EID_FITR + EID_ADHA):
            day_f *= 0.72
        if near(d, EID_ADHA, before=3, after=-1):
            day_f *= 1.3
        if d.day <= 4 or d.day >= 27:
            day_f *= 1.08
        pay = [0.62 - 0.14 * progress, 0.27 + 0.07 * progress, 0.07 + 0.06 * progress, 0.04 + 0.01 * progress]
        for b in branches:
            n = max(5, int(RNG.gauss(b["base_tx"] * day_f, b["base_tx"] * day_f * 0.09)))
            staff = employees[b["id"]]
            for _ in range(n):
                hour = RNG.choices(hk, hw)[0]
                minute, sec = RNG.randint(0, 59), RNG.randint(0, 59)
                day = d + dt.timedelta(days=1) if hour <= 1 and not pharmacy and hour < 7 else d
                ts = dt.datetime(day.year, day.month, day.day, hour, minute, sec, tzinfo=AMMAN)
                shift = "am" if 6 <= hour < 15 else "pm"
                pool_ = [e for e in staff if e["shift"] in (shift, "any")] or staff
                cashier = RNG.choice(pool_)
                k = 1 + min(14, int(RNG.expovariate(1 / (items_mean * (1.3 if rm is not None else 1) - 1 + 1e-9))))
                chosen = {}
                for idx in RNG.choices(range(len(prods)), cum_weights=cum, k=k):
                    chosen[idx] = chosen.get(idx, 0) + 1
                sale_id = uid()
                seq[b["id"]] += 1
                subtotal = tax = 0.0
                lines = []
                for idx, cnt in chosen.items():
                    p = prods[idx]
                    q = cnt
                    if p["cat"] in ("water", "beverages") and "can" in p["size"] and RNG.random() < 0.25:
                        q *= RNG.choice([2, 3, 4, 6])
                    elif p["cat"] == "bakery" and RNG.random() < 0.35:
                        q *= 2
                    unit_cost = p["cost"]
                    if p["id"] in below_cost and d >= below_cost[p["id"]][0]:
                        unit_cost = below_cost[p["id"]][1]
                    elif p.get("old_cost") and d < p["cost_change"]:
                        unit_cost = p["old_cost"]
                    lt = r3(q * p["price"])
                    subtotal += lt
                    tax += lt - lt / (1 + p["tax"] / 100)
                    lines.append((p, q, unit_cost, lt))
                disc = 0.0
                rate = 0.0
                if cashier["id"] == bad_cashier and d >= bad_since and RNG.random() < 0.24:
                    rate = RNG.choice([0.10, 0.12, 0.15, 0.2])
                elif RNG.random() < 0.035:
                    rate = 0.05
                disc = r3(subtotal * rate)
                status = "completed"
                vr = 0.034 if (cashier["id"] == bad_cashier and d >= bad_since) else 0.005
                x = RNG.random()
                if x < vr:
                    status = "void"
                elif x < vr + 0.003:
                    status = "returned"
                cust = None
                if cust_ids and RNG.random() < (0.5 if pharmacy else 0.44):
                    for _try in range(3):
                        c = RNG.choices(cust_ids, cust_w)[0]
                        if not (c in churned and d >= churn_date):
                            cust = c
                            break
                total = r3(subtotal - disc)
                tax_v = r3(tax * (1 - rate))
                pm = RNG.choices(["cash", "card", "cliq", "wallet"], pay)[0]
                inv = f"{b['code']}-{d.year}-{seq[b['id']]:06d}"
                sales.append((sale_id, org_id, b["id"], cashier["id"], cust, inv, ts, r3(subtotal), disc, tax_v, total, pm, status))
                for p, q, uc, lt in lines:
                    ld = r3(lt * rate)
                    items.append((uid(), org_id, sale_id, p["id"], float(q), p["price"], uc, ld, r3(lt - ld)))
                    if status == "completed":
                        sold[(b["id"], p["id"], d)] += q
        d += dt.timedelta(days=1)
    return sales, items, sold


def plant_compliance(sales, branch_id):
    idxs = [i for i, s in enumerate(sales) if s[2] == branch_id and (END - s[6].date()).days < 120]
    RNG.shuffle(idxs)
    for i in idxs[:9]:
        s = list(sales[i]); s[9] = 0.0; sales[i] = tuple(s)
    for i in idxs[9:12]:
        j = idxs[RNG.randint(20, 200)]
        s = list(sales[i]); s[5] = sales[j][5]; sales[i] = tuple(s)
    for i in idxs[12:19]:
        s = list(sales[i]); pre, yr, n = s[5].split("-"); s[5] = f"{pre}-{yr}-{int(n) + 900000:06d}"; sales[i] = tuple(s)


def build_purchases(org_id, branches, prods, sold, start, end, sup_ids, shrink_branch=None):
    purchases, pitems, stock, last_line = [], [], {}, {}
    by_sup = defaultdict(list)
    for p in prods:
        by_sup[p["supplier_key"]].append(p)
    sold_total = defaultdict(float)
    for (bid, pid, _), q in sold.items():
        sold_total[(bid, pid)] += q
    po = 0
    for b in branches:
        week = start - dt.timedelta(days=3)
        first = True
        while week <= end:
            nxt = week + dt.timedelta(days=7)
            for sk, plist in by_sup.items():
                lines = []
                for p in plist:
                    if first:
                        q = sum(sold.get((b["id"], p["id"], start + dt.timedelta(days=i)), 0) for i in range(14))
                        q = math.ceil(q * 1.15) + RNG.randint(2, 8)
                        if p["dead"]:
                            q += int(RNG.randint(14, 40) * (1 if p["price"] < 20 else 0.25)) + 2
                    else:
                        q = sum(sold.get((b["id"], p["id"], week + dt.timedelta(days=3 + i)), 0) for i in range(7))
                        if q <= 0:
                            continue
                        q = math.ceil(q * RNG.uniform(1.0, 1.12))
                    if p["cat"] in ("water", "beverages"):
                        q = int(math.ceil(q / 6) * 6)
                    lines.append((p, q))
                if not lines:
                    continue
                po += 1
                pid = uid()
                od = dt.datetime(week.year, week.month, week.day, 10, 0, tzinfo=AMMAN)
                status, rcv = "received", od + dt.timedelta(days=RNG.randint(1, 2))
                if nxt > end and RNG.random() < 0.4:
                    status, rcv = "sent", None
                tot = 0.0
                for p, q in lines:
                    uc = p["old_cost"] if p.get("cost_change") and week < p["cost_change"] else p["cost"]
                    lt = r3(q * uc)
                    tot += lt
                    pitems.append([uid(), org_id, pid, p["id"], float(q), uc, lt])
                    if status == "received":
                        stock[(b["id"], p["id"])] = stock.get((b["id"], p["id"]), 0) + q
                        last_line[(b["id"], p["id"])] = len(pitems) - 1
                purchases.append((pid, org_id, b["id"], sup_ids[sk], f"PO-{od.year}-{po:05d}", od, rcv, r3(tot), status))
            week = nxt
            first = False
    for key in list(stock):
        stock[key] -= sold_total.get(key, 0)
        p = next(x for x in prods if x["id"] == key[1])
        if key[0] == shrink_branch and p["cat"] in ("sweets", "personal"):
            stock[key] -= math.floor(sold_total.get(key, 0) * 0.07)
    return purchases, pitems, stock, last_line


async def copy(conn, table, cols, recs):
    if recs:
        await conn.copy_records_to_table(table, records=recs, columns=cols)
    print(f"  {table:<18} {len(recs):>8,}")


async def seed_tenant(conn, cfg, users):
    org_id = uid()
    await conn.execute(
        """insert into organizations(id,name,name_ar,slug,industry,city,plan,tax_number,onboarding_completed,is_demo,created_at,locale)
           values($1,$2,$3,$4,$5,$6,$7,$8,true,true,$9,'ar')""",
        org_id, cfg["name"], cfg["name_ar"], cfg["slug"], cfg["industry"], cfg["city"], cfg["plan"], cfg.get("tax_number"),
        dt.datetime.combine(cfg["start"] - dt.timedelta(days=20), dt.time(9), AMMAN))
    for email, role in cfg["members"]:
        await conn.execute("insert into memberships(org_id,user_id,role) values($1,$2,$3)", org_id, users[email], role)

    branches = []
    for code, name, name_ar, area, lat, lng, base_tx in cfg["branches"]:
        bid = uid()
        branches.append(dict(id=bid, code=code, name=name, base_tx=base_tx))
        await conn.execute("insert into branches(id,org_id,name,name_ar,city,area,lat,lng,opened_at) values($1,$2,$3,$4,$5,$6,$7,$8,$9)",
                           bid, org_id, name, name_ar, cfg["city"], area, lat, lng, dt.date(RNG.randint(2014, 2021), RNG.randint(1, 12), 1))

    emp_rows, employees = [], {b["id"]: [] for b in branches}
    for b in branches:
        for title, shift, count in cfg["staffing"]:
            for _ in range(count):
                g, n, na = person("M" if title in ("stock_keeper",) else None)
                if cfg.get("bad_cashier_branch") == b["code"] and title == "cashier" and not any(e.get("bad") for e in employees[b["id"]]):
                    n, na, g = "Odai Al-Shboul", "عدي الشبول", "M"
                    e = dict(id=uid(), shift="pm", bad=True)
                else:
                    e = dict(id=uid(), shift=shift if title == "cashier" else "any")
                if title == "cashier" and shift == "split":
                    e["shift"] = RNG.choice(["am", "pm"])
                employees[b["id"]].append(e) if title in ("cashier", "supervisor", "pharmacist") else None
                emp_rows.append((e["id"], org_id, b["id"], n, na, title, jo_mobile(), None,
                                 dt.date(RNG.randint(2018, 2025), RNG.randint(1, 12), RNG.randint(1, 28)),
                                 float(RNG.choice(cfg["salaries"][title])), True))
    await copy(conn, "employees", ["id", "org_id", "branch_id", "full_name", "full_name_ar", "job_title", "phone", "email", "hired_at", "monthly_salary", "is_active"], emp_rows)
    bad_cashier = next((e["id"] for es in employees.values() for e in es if e.get("bad")), None)

    cust_rows, customers = [], []
    areas = C.AREAS[cfg["city"]]
    for i in range(cfg["customers"]):
        g, n, na = person()
        cid = uid()
        w = 1 / (i + 8) ** 0.85
        customers.append(dict(id=cid, w=w))
        first, last = n.lower().split(" ", 1)
        email = f"{first}.{last.replace(' ', '').replace('-', '')}{RNG.randint(1, 99)}@example.com" if RNG.random() < 0.4 else None
        area = RNG.choice(areas)
        cust_rows.append((cid, org_id, n, na, jo_mobile(), email, g, cfg["city"], area[0], f"{cfg['card']}-{100000 + i * 7 + RNG.randint(0, 6)}", 0,
                          cfg["start"] + dt.timedelta(days=RNG.randint(0, 200))))
    await copy(conn, "customers", ["id", "org_id", "full_name", "full_name_ar", "phone", "email", "gender", "city", "area", "loyalty_card", "loyalty_points", "first_seen"], cust_rows)
    churned = set(c["id"] for c in customers[3:17]) if cfg.get("churn") else set()

    sup_ids = {}
    sup_rows = []
    for key, (name, name_ar, contact, cat, terms) in cfg["suppliers"].items():
        sid = uid()
        sup_ids[key] = sid
        slug = "".join(ch for ch in name.lower() if ch.isalnum())[:14]
        sup_rows.append((sid, org_id, name, name_ar, contact, jo_mobile().replace("+9627", "+9626", 1) if RNG.random() < 0.3 else jo_mobile(),
                         f"orders@{slug}.example.com", terms, cat))
    await copy(conn, "suppliers", ["id", "org_id", "name", "name_ar", "contact_name", "phone", "email", "payment_terms_days", "category"], sup_rows)
    cats = {}
    for key, en, ar, tax in cfg["categories"]:
        cats[key] = dict(id=uid(), tax=tax)
        await conn.execute("insert into categories(id,org_id,name,name_ar) values($1,$2,$3,$4)", cats[key]["id"], org_id, en, ar)
    prods = build_products(cfg["products"], cats)

    below_cost = {}
    for base in cfg.get("below_cost", []):
        for p in prods:
            if p["base"] == base:
                when = END - dt.timedelta(days=RNG.randint(95, 125))
                new_cost = r3(p["price"] * RNG.uniform(1.04, 1.09))
                below_cost[p["id"]] = (when, new_cost)
                p["old_cost"], p["cost_change"], p["below_cost_from"] = p["cost"], when, when
                p["cost"] = new_cost
                break
    for p in prods:
        if p["supplier_key"] == cfg.get("price_rise_supplier") and p["id"] not in below_cost:
            p["old_cost"], p["cost_change"] = p["cost"], END - dt.timedelta(days=70)
            p["cost"] = r3(p["cost"] * 1.09)

    prod_rows = [(p["id"], org_id, p["category_id"], sup_ids[p["supplier_key"]], p["sku"], p["barcode"], p["name"], p["name_ar"], p["brand"],
                  "pcs", p["size"], p["cost"], p["price"], float(p["tax"]), max(6, int(p["pop"] * 4)), p["perishable"], p["shelf"], True) for p in prods]
    await copy(conn, "products", ["id", "org_id", "category_id", "supplier_id", "sku", "barcode", "name", "name_ar", "brand", "unit", "size", "cost",
                                  "price", "tax_rate", "reorder_level", "is_perishable", "shelf_life_days", "is_active"], prod_rows)
    alias_rows = []
    for p in prods:
        alias_rows.append((uid(), org_id, p["id"], p["name_ar"], "catalog"))
    await copy(conn, "product_aliases", ["id", "org_id", "product_id", "alias", "source"], alias_rows)

    print(f"  simulating {cfg['name']} …")
    sales, items, sold = simulate(org_id, branches, prods, employees, customers, cfg["start"], END, cfg["mult"], cfg["items_mean"],
                                  pharmacy=cfg["industry"] == "pharmacy",
                                  planted={"churned": churned, "below_cost": below_cost, "bad_cashier": bad_cashier})
    if cfg.get("compliance_branch"):
        plant_compliance(sales, next(b["id"] for b in branches if b["code"] == cfg["compliance_branch"]))
    await copy(conn, "sales", ["id", "org_id", "branch_id", "employee_id", "customer_id", "invoice_number", "sold_at", "subtotal", "discount", "tax", "total", "payment_method", "status"], sales)
    await copy(conn, "sale_items", ["id", "org_id", "sale_id", "product_id", "quantity", "unit_price", "unit_cost", "discount", "line_total"], items)

    await conn.execute("""update customers c set loyalty_points = coalesce(x.pts,0) from
                          (select customer_id, floor(sum(total))::int pts from sales where org_id=$1 and status='completed' group by 1) x
                          where c.id = x.customer_id""", org_id)

    shrink_branch = next((b["id"] for b in branches if b["code"] == cfg.get("shrink_branch")), None)
    purchases, pitems, stock, last_line = build_purchases(org_id, branches, prods, sold, cfg["start"], END, sup_ids, shrink_branch)

    def adjust_last_po(key, delta):
        i = last_line.get(key)
        if i is not None:
            pitems[i][4] = max(0.0, pitems[i][4] + delta)
            pitems[i][6] = r3(pitems[i][4] * pitems[i][5])

    inv_rows, batch_rows = [], []
    low_targets = set(RNG.sample([p["id"] for p in prods if p["pop"] >= 4], k=min(22, len(prods) // 6)))
    expiring_left = 38 if cfg["industry"] == "minimarket" else 14
    for b in branches:
        for p in prods:
            key = (b["id"], p["id"])
            q = stock.get(key, 0)
            if q < 0:
                new = RNG.randint(0, 3)
                if b["id"] != shrink_branch:
                    adjust_last_po(key, new - q)
                q = new
            if p["id"] in low_targets and RNG.random() < 0.6:
                new = RNG.randint(0, max(1, int(p["pop"] * 1.5)))
                if new < q:
                    adjust_last_po(key, new - q)
                    q = new
            q = float(round(q))
            inv_rows.append((uid(), org_id, b["id"], p["id"], q))
            if q > 0 and p["shelf"]:
                if p["perishable"] and expiring_left > 0 and RNG.random() < 0.35:
                    exp = END + dt.timedelta(days=RNG.randint(-2, 13))
                    expiring_left -= 1
                elif cfg["industry"] == "pharmacy" and expiring_left > 0 and RNG.random() < 0.12:
                    exp = END + dt.timedelta(days=RNG.randint(5, 40))
                    expiring_left -= 1
                else:
                    exp = END + dt.timedelta(days=RNG.randint(max(15, p["shelf"] // 3), max(16, p["shelf"])))
                batch_rows.append((uid(), org_id, b["id"], p["id"], q, exp, END - dt.timedelta(days=RNG.randint(1, 10))))
    tot_by_po = defaultdict(float)
    for it in pitems:
        tot_by_po[it[2]] += it[6]
    purchases = [(*p[:7], r3(tot_by_po[p[0]]), p[8]) for p in purchases]
    await copy(conn, "purchases", ["id", "org_id", "branch_id", "supplier_id", "po_number", "ordered_at", "received_at", "total", "status"], purchases)
    await copy(conn, "purchase_items", ["id", "org_id", "purchase_id", "product_id", "quantity", "unit_cost", "line_total"], [tuple(x) for x in pitems])
    await copy(conn, "inventory_levels", ["id", "org_id", "branch_id", "product_id", "quantity"], inv_rows)
    await copy(conn, "inventory_batches", ["id", "org_id", "branch_id", "product_id", "quantity", "expiry_date", "received_at"], batch_rows)

    rev = await conn.fetch("""select branch_id, date_trunc('month', sold_at at time zone 'Asia/Amman')::date m, sum(total)::float t
                              from sales where org_id=$1 and status='completed' group by 1,2""", org_id)
    by_b = defaultdict(dict)
    for r in rev:
        by_b[r["branch_id"]][r["m"]] = r["t"]
    goal_rows = []
    this_month = END.replace(day=1)
    for bid, months in by_b.items():
        ms = sorted(months)
        for m in sorted(set(ms[-6:]) | {this_month}):
            prev = [months[x] for x in ms if x < m][-3:]
            if not prev:
                continue
            base = sum(prev) / len(prev)
            goal_rows.append((uid(), org_id, bid, "revenue", m, r3(round(base * RNG.uniform(1.03, 1.08), -2))))
    await copy(conn, "goals", ["id", "org_id", "branch_id", "metric", "period_month", "target"], goal_rows)

    owner = users[cfg["members"][0][0]]
    await conn.executemany("insert into alert_rules(org_id,name,metric,operator,threshold,channel,created_by) values($1,$2,$3,$4,$5,$6,$7)", [
        (org_id, "Top sellers running low", "stock_below_reorder", ">", 5, "email", owner),
        (org_id, "Daily sales drop more than 20%", "daily_sales_drop_pct", ">", 20, "in_app", owner),
        (org_id, "Discounts above 6% of sales", "discount_rate_pct", ">", 6, "in_app", owner),
        (org_id, "Items expiring within 7 days", "expiring_items", ">", 0, "email", owner),
    ])
    return org_id, branches, prods, owner


MINIMARKET = dict(
    name="Al-Nashama Market", name_ar="أسواق النشامى", slug="al-nashama", industry="minimarket", city="Amman", plan="growth",
    tax_number="117845239", card="NSH",
    members=[("owner@nashama.example.com", "owner"), ("manager@nashama.example.com", "manager"),
             ("accountant@nashama.example.com", "accountant"), ("cashier@nashama.example.com", "cashier"),
             ("founder@idrak.example.com", "owner")],
    branches=[("KH", "Khalda", "خلدا", "Wasfi Al-Tal St.", 31.9993, 35.8487, 92),
              ("SW", "Sweifieh", "الصويفية", "Wakalat St.", 31.9566, 35.8636, 80),
              ("JH", "Jabal Al-Hussein", "جبل الحسين", "Khalid Bin Al-Walid St.", 31.9681, 35.9157, 66)],
    staffing=[("supervisor", "any", 1), ("cashier", "am", 1), ("cashier", "pm", 2), ("stock_keeper", "any", 1)],
    salaries={"supervisor": [620, 650, 700], "cashier": [380, 400, 420, 450], "stock_keeper": [350, 370, 390]},
    customers=460, suppliers=C.SUPPLIERS, categories=C.CATEGORIES, products=C.P, mult=minimarket_mult, items_mean=3.2,
    start=END - dt.timedelta(days=370), churn=True, bad_cashier_branch="SW", compliance_branch="JH", shrink_branch="JH",
    below_cost=["Kinder Bueno", "Kinder Joy", "Pringles Original", "Kiri Cheese Squares", "Heinz Tomato Ketchup", "Dettol Antiseptic Liquid"],
    price_rise_supplier="gulfbev",
)
PHARMACY = dict(
    name="Al-Shifa Pharmacy", name_ar="صيدلية الشفاء", slug="al-shifa", industry="pharmacy", city="Irbid", plan="starter",
    tax_number=None, card="SHF",
    members=[("owner@alshifa.example.com", "owner")],
    branches=[("SH", "University Street", "شارع الجامعة", "University St.", 32.5363, 35.8596, 46)],
    staffing=[("pharmacist", "any", 2), ("cashier", "split", 2)],
    salaries={"pharmacist": [750, 800, 850], "cashier": [380, 400]},
    customers=170, suppliers=C.PHARMA_SUPPLIERS, categories=C.PHARMA_CATEGORIES, products=C.PHARMA, mult=pharmacy_mult, items_mean=1.8,
    start=END - dt.timedelta(days=182),
)

EXTRA_TENANTS = [
    ("Bayt Al-Kheir Market", "سوق بيت الخير", "minimarket", "Zarqa", "growth", 160),
    ("Zahrat Al-Sharq Sweets", "حلويات زهرة الشرق", "restaurant", "Madaba", "starter", 120),
    ("Al-Amal Pharmacy", "صيدلية الأمل", "pharmacy", "Salt", "starter", 95),
    ("Qahwat Al-Balad Cafe", "قهوة البلد", "restaurant", "Amman", "growth", 80),
    ("Rose Boutique", "روز بوتيك", "fashion", "Amman", "starter", 64),
    ("Al-Wadi Mini Market", "ميني ماركت الوادي", "minimarket", "Aqaba", "growth", 41),
    ("Sanabel Bakery", "مخابز سنابل", "restaurant", "Irbid", "business", 33),
    ("Green Basket Organics", "السلة الخضراء", "minimarket", "Amman", "growth", 19),
    ("Lamsa Optics", "لمسة للبصريات", "fashion", "Amman", "starter", 7),
]


async def main():
    # هذا السكربت ينشئ حسابات بكلمة مرور مشتركة، ويحذف صفوفاً من
    # waitlist و health_checks و contact_messages. لا يجوز تشغيله على بيئة
    # إنتاج. الحارس صريح بدل الاعتماد على الانتباه.
    if os.getenv("IDRAK_ALLOW_SEED") != "yes":
        sys.exit(
            "Refusing to seed: this creates shared-password demo accounts and "
            "deletes rows from waitlist, health_checks and contact_messages.\n"
            "Set IDRAK_ALLOW_SEED=yes only on a disposable environment."
        )
    print("Creating demo users …")
    users = await ensure_users()
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0, command_timeout=600)
    import json
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    try:
        print("Removing old demo tenants …")
        await conn.execute("delete from organizations where is_demo")
        await conn.execute("delete from waitlist; delete from health_checks; delete from contact_messages where email like '%example.com'")
        for email, name, name_ar, sup in DEMO_USERS:
            await conn.execute("""insert into profiles(id,full_name,locale,is_super_admin) values($1,$2,'ar',$3)
                                  on conflict (id) do update set full_name=excluded.full_name, is_super_admin=excluded.is_super_admin""",
                               users[email], name, sup)

        print("Tenant 1: Al-Nashama Market")
        org1, br1, prods1, owner1 = await seed_tenant(conn, MINIMARKET, users)
        print("Tenant 2: Al-Shifa Pharmacy")
        org2, br2, prods2, owner2 = await seed_tenant(conn, PHARMACY, users)

        for fname, ent, hb, ha, rowsn, days in [("pos_export_october.xlsx", "sales", 41.0, 97.2, 4120, 33), ("supplier_prices_2026.csv", "products", 58.4, 99.1, 212, 61),
                                               ("customers_from_whatsapp.csv", "customers", 37.5, 94.6, 389, 90)]:
            await conn.execute("""insert into uploads(org_id,uploaded_by,file_name,file_size,entity,row_count,column_count,status,health_before,health_after,imported_rows,created_at)
                                  values($1,$2,$3,$4,$5,$6,$7,'imported',$8,$9,$6,$10)""",
                               org1, users["manager@nashama.example.com"], fname, rowsn * 140, ent, rowsn, 9, hb, ha,
                               dt.datetime.combine(END - dt.timedelta(days=days), dt.time(11, 20), AMMAN))
        rules = [("payment_method", "فيزا", "card"), ("payment_method", "كاش", "cash"), ("branch", "فرع خلدا", "Khalda"), ("branch", "صويفيه", "Sweifieh"),
                 ("product", "ببسي ٣٣٠", "Pepsi 330ml can"), ("product", "مياه غدير صغير", "Ghadeer Water 600ml"), ("city", "عمان الغربية", "Amman")]
        await conn.executemany("insert into cleaning_rules(org_id,column_kind,match_value,replace_value,rule_type,times_applied,created_by) values($1,$2,$3,$4,'value_map',$5,$6)",
                               [(org1, a, b, c, RNG.randint(3, 140), users["manager@nashama.example.com"]) for a, b, c in rules])

        now = dt.datetime.now(AMMAN)
        notes = [("leak", "6 products are being sold below cost", "/app/insights/leaks", 2), ("stock", "14 top sellers are below reorder level", "/app/insights/reorder", 5),
                 ("expiry", "38 items expire within 14 days", "/app/products?filter=expiring", 9), ("digest", "Your weekly digest is ready", "/app/reports", 26),
                 ("cleaning", "pos_export_october.xlsx cleaned: 41 → 97", "/app/data", 33 * 24), ("team", "Mahmoud Obeidat joined as Accountant", "/app/settings/team", 40 * 24)]
        await conn.executemany("insert into notifications(org_id,kind,title,link,created_at,read_at) values($1,$2,$3,$4,$5,$6)",
                               [(org1, k, t, l, now - dt.timedelta(hours=h), None if h < 10 else now - dt.timedelta(hours=h - 1)) for k, t, l, h in notes])
        acts = [("login", None), ("upload.created", "pos_export_october.xlsx"), ("cleaning.applied", "pos_export_october.xlsx"), ("team.invited", "accountant@nashama.example.com"),
                ("alert.created", "Top sellers running low"), ("report.exported", "Monthly summary"), ("purchase.emailed", "Pepsi Jordan Distribution"),
                ("settings.updated", "Tax number"), ("insight.dismissed", "Dead stock: Philips LED Bulb")]
        audit = []
        for i in range(36):
            a, ent = RNG.choice(acts)
            u = RNG.choice(["owner@nashama.example.com", "manager@nashama.example.com", "accountant@nashama.example.com"])
            audit.append((org1, users[u], a, ent, now - dt.timedelta(hours=RNG.randint(1, 24 * 60))))
        await conn.executemany("insert into audit_log(org_id,user_id,action,entity,created_at) values($1,$2,$3,$4,$5)", audit)

        for name, name_ar, ind, city, plan, age in EXTRA_TENANTS:
            await conn.execute("insert into organizations(name,name_ar,industry,city,plan,is_demo,onboarding_completed,created_at) values($1,$2,$3,$4,$5,true,true,$6)",
                               name, name_ar, ind, city, plan, now - dt.timedelta(days=age))

        biz = ["mini market", "pharmacy", "restaurant", "bakery", "fashion", "cafe", "electronics", "sweets"]
        cities = ["Amman", "Irbid", "Zarqa", "Aqaba", "Salt", "Madaba", "Jerash", "Karak", "Riyadh", "Dubai"]
        wl = []
        for i in range(73):
            g, n, na = person()
            first, last = n.lower().split(" ", 1)
            wl.append((f"{first}.{last.replace(' ', '').replace('-', '')}{i}@example.com", n, f"{RNG.choice(C.FAMILY)[0].replace('Al-', '')} {RNG.choice(biz).title()}",
                       RNG.choice(biz), RNG.choice(cities), RNG.choice(["ar", "ar", "en"]), now - dt.timedelta(hours=RNG.randint(2, 24 * 75))))
        await conn.executemany("insert into waitlist(email,name,business_name,business_type,city,locale,created_at) values($1,$2,$3,$4,$5,$6,$7)", wl)
        await conn.executemany("insert into health_checks(file_name,row_count,score,created_at) values($1,$2,$3,$4)",
                               [(RNG.choice(["sales.xlsx", "inventory.csv", "customers.xlsx", "export.csv"]), RNG.randint(80, 9000), round(RNG.uniform(22, 71), 1),
                                 now - dt.timedelta(hours=RNG.randint(1, 24 * 60))) for _ in range(214)])
        ai = []
        for i in range(60):
            day = now - dt.timedelta(days=i)
            for _ in range(RNG.randint(8, 30)):
                it, ot = RNG.randint(1800, 9000), RNG.randint(150, 900)
                ai.append((RNG.choice([org1, org1, org2]), owner1, settings.gemini_model, RNG.choice(["chat", "chat", "mapping", "insight"]), it, ot,
                           round(it * 0.30 / 1e6 + ot * 2.5 / 1e6, 5), day - dt.timedelta(minutes=RNG.randint(0, 900))))
        await conn.executemany("insert into ai_usage(org_id,user_id,model,kind,input_tokens,output_tokens,cost_usd,created_at) values($1,$2,$3,$4,$5,$6,$7,$8)", ai)
        print("Analyzing tables …")
        await conn.execute("analyze sales; analyze sale_items; analyze products; analyze inventory_levels;")
    finally:
        await conn.close()

    from seed.fix_stock_consistency import main as fix_stock
    await fix_stock()
    from seed.messy import write_messy_files
    await write_messy_files()
    print(f"\nDone. Demo password for all demo accounts: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())

from .. import db
from .arabic import match_key
from .engine import Context


async def load_context(org_id: str) -> Context:
    prods = await db.fetch("""select p.name, p.name_ar, coalesce(array_agg(a.alias) filter (where a.alias is not null), '{}') aliases
                              from products p left join product_aliases a on a.product_id=p.id
                              where p.org_id=$1 group by p.id""", org_id)
    branches = await db.fetch("select name, name_ar, area from branches where org_id=$1", org_id)
    emps = await db.fetch("select full_name, full_name_ar from employees where org_id=$1", org_id)
    rules = await db.fetch("select column_kind, match_value, replace_value from cleaning_rules where org_id=$1", org_id)
    kind_alias = {"payment_method": "payment", "product": "product", "branch": "branch", "city": "city", "cashier": "person", "area": "area"}
    return Context(
        products=[{"name": p["name"], "keys": [p["name"], p["name_ar"] or "", *p["aliases"]]} for p in prods],
        branches=[{"name": b["name"], "keys": [b["name"], b["name_ar"] or "", f"فرع {b['name_ar']}", f"{b['name']} branch"]} for b in branches],
        employees=[{"name": e["full_name"], "keys": [e["full_name"], e["full_name_ar"] or ""]} for e in emps],
        rules={(kind_alias.get(r["column_kind"], r["column_kind"]), match_key(r["match_value"])): r["replace_value"] for r in rules},
    )

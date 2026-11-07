import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import asyncpg

from app.config import settings


async def main():
    c = await asyncpg.connect(settings.database_url, statement_cache_size=0)
    gaps = await c.fetch("""
        with recv as (select pu.branch_id, pi.product_id, sum(pi.quantity) q from purchase_items pi join purchases pu on pu.id=pi.purchase_id
                      where pu.status='received' group by 1,2),
             sold as (select s.branch_id, si.product_id, sum(si.quantity) q from sale_items si join sales s on s.id=si.sale_id
                      where s.status='completed' group by 1,2)
        select r.branch_id, r.product_id, (r.q - coalesce(sd.q,0)) - il.quantity gap
        from recv r join inventory_levels il on il.branch_id=r.branch_id and il.product_id=r.product_id
        left join sold sd on sd.branch_id=r.branch_id and sd.product_id=r.product_id
        join products p on p.id=r.product_id join branches b on b.id=r.branch_id left join categories cat on cat.id=p.category_id
        join organizations o on o.id=b.org_id
        where o.is_demo and (r.q - coalesce(sd.q,0)) - il.quantity <> 0
          and not (b.name='Jabal Al-Hussein' and cat.name in ('Chocolate & Sweets','Personal Care'))""")
    fixed = 0
    async with c.transaction():
        for g in gaps:
            remaining = float(g["gap"])
            lines = await c.fetch("""select pi.id, pi.quantity, pi.unit_cost from purchase_items pi join purchases pu on pu.id=pi.purchase_id
                                     where pu.branch_id=$1 and pi.product_id=$2 and pu.status='received' order by pu.ordered_at desc""", g["branch_id"], g["product_id"])
            for ln in lines:
                if abs(remaining) < 0.001:
                    break
                q = float(ln["quantity"])
                new_q = max(0.0, q - remaining)
                remaining -= (q - new_q)
                await c.execute("update purchase_items set quantity=$2, line_total=round($2*unit_cost, 3) where id=$1", ln["id"], new_q)
            fixed += 1
        await c.execute("""update purchases pu set total = coalesce((select sum(line_total) from purchase_items pi where pi.purchase_id=pu.id),0)
                           where pu.org_id in (select id from organizations where is_demo)""")
    print(f"adjusted {fixed} product/branch purchase histories")
    await c.close()


if __name__ == "__main__":
    asyncio.run(main())

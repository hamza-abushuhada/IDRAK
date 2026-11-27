"""Net-of-returns accounting, shared by every report (SQL fragments over a `sales s` alias).

Data model (all sources): a sale with status 'returned' is a RETURN DOCUMENT, separate
from the original sale, which stays 'completed' (file imports: negative lines; Demo POS;
Loyverse REFUND receipts; Lab refunds from now on). Therefore:

    gross sales  = completed totals
    refunds      = returned totals
    net sales    = gross - refunds          (what reports show as "sales"/"revenue")
    net profit   = profit of completed lines - profit of returned lines
    net units    = completed quantities - returned quantities

Legacy exception: older Lab refunds switched the ORIGINAL invoice itself to 'returned'
(whole order, no completed twin). Such a row is both the sale and its refund: it counts
once in gross and once in refunds, so its net effect is zero (never deducted twice).
Void sales never count. Transaction counts, discounts and customers stay on completed
sales (they describe customer operations, not money kept).
"""

# A whole-order Lab refund recorded on the original invoice (no completed twin).
LAB_FLIP = """(s.status='returned' and s.pos_connection_id is not null
  and exists (select 1 from pos_connections pc where pc.id=s.pos_connection_id and pc.provider_code in ('lab_pos','lab_web'))
  and not exists (select 1 from sales o where o.org_id=s.org_id and o.invoice_number is not distinct from s.invoice_number and o.status='completed'))"""

# +1 sale, -1 return document, 0 void / legacy Lab whole-order refund.
SIGN = f"(case when s.status='completed' then 1 when s.status='returned' and not {LAB_FLIP} then -1 else 0 end)"

# Rows that take part in money/quantity totals.
COUNTED = "s.status in ('completed','returned')"

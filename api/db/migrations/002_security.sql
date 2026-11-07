do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
  end loop;
end $$;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'basira_ai_reader') then
    create role basira_ai_reader nologin;
  end if;
end $$;
grant basira_ai_reader to postgres;
grant usage on schema public to basira_ai_reader;

do $$
declare t text;
begin
  foreach t in array array['branches','employees','customers','suppliers','categories','products',
                           'inventory_levels','inventory_batches','sales','sale_items','purchases',
                           'purchase_items','goals','insights'] loop
    execute format('grant select on public.%I to basira_ai_reader', t);
    execute format('drop policy if exists ai_tenant_read on public.%I', t);
    execute format($p$create policy ai_tenant_read on public.%I for select to basira_ai_reader
                    using (org_id = nullif(current_setting('app.org_id', true), '')::uuid)$p$, t);
  end loop;
end $$;

create or replace view v_sales with (security_invoker = true) as
select s.id as sale_id, s.org_id, s.invoice_number, s.sold_at, (s.sold_at at time zone 'Asia/Amman')::date as sale_date,
       b.name as branch, e.full_name as cashier, c.full_name as customer,
       s.subtotal, s.discount, s.tax, s.total, s.payment_method, s.status
from sales s
left join branches b on b.id = s.branch_id
left join employees e on e.id = s.employee_id
left join customers c on c.id = s.customer_id;

create or replace view v_sale_lines with (security_invoker = true) as
select si.org_id, s.sold_at, (s.sold_at at time zone 'Asia/Amman')::date as sale_date, b.name as branch,
       e.full_name as cashier, p.name as product, p.name_ar as product_ar, cat.name as category,
       si.quantity, si.unit_price, si.unit_cost, si.discount, si.line_total,
       round(si.line_total - si.unit_cost * si.quantity, 3) as gross_profit, s.status
from sale_items si
join sales s on s.id = si.sale_id
left join products p on p.id = si.product_id
left join categories cat on cat.id = p.category_id
left join branches b on b.id = s.branch_id
left join employees e on e.id = s.employee_id;

create or replace view v_inventory with (security_invoker = true) as
select il.org_id, b.name as branch, p.name as product, p.name_ar as product_ar, cat.name as category,
       il.quantity, p.reorder_level, p.cost, p.price, round(il.quantity * p.cost, 3) as stock_value_cost
from inventory_levels il
join products p on p.id = il.product_id
join branches b on b.id = il.branch_id
left join categories cat on cat.id = p.category_id;

create or replace view v_products with (security_invoker = true) as
select p.org_id, p.id as product_id, p.sku, p.barcode, p.name, p.name_ar, p.brand, cat.name as category,
       sup.name as supplier, p.cost, p.price,
       case when p.price > 0 then round((p.price - p.cost) / p.price * 100, 1) end as margin_pct,
       p.reorder_level, p.is_perishable, p.is_active
from products p
left join categories cat on cat.id = p.category_id
left join suppliers sup on sup.id = p.supplier_id;

create or replace view v_purchases with (security_invoker = true) as
select pu.org_id, pu.po_number, pu.ordered_at, pu.received_at, pu.status, sup.name as supplier, b.name as branch,
       p.name as product, pi.quantity, pi.unit_cost, pi.line_total
from purchase_items pi
join purchases pu on pu.id = pi.purchase_id
left join suppliers sup on sup.id = pu.supplier_id
left join branches b on b.id = pu.branch_id
left join products p on p.id = pi.product_id;

grant select on v_sales, v_sale_lines, v_inventory, v_products, v_purchases to basira_ai_reader;
revoke all on v_sales, v_sale_lines, v_inventory, v_products, v_purchases from anon, authenticated;

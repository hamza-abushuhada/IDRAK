"""Tests for sql_guard.validate — stdlib unittest only, no DB, no model, no deps.

Run:  python -I -m unittest discover -s security-fixes -p 'test_*.py'
  or: python -I security-fixes/api/app/services/test_sql_guard.py

These are the regression cases the audit called for. The first class is the
boundary: every string the old guard wrongly admitted must now be rejected.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sql_guard  # noqa: E402
from sql_guard import SqlRejected, validate  # noqa: E402


class TestRejectsTheAuditBypasses(unittest.TestCase):
    """The strings the denylist let through. Each must now raise."""

    def test_set_config_bare(self):
        with self.assertRaises(SqlRejected):
            validate("select set_config('app.org_id','00000000-0000-0000-0000-000000000000',true)")

    def test_set_config_in_cte_joined_to_allowed_table(self):
        # The working exploit shape: rebind and read co-located in one statement.
        with self.assertRaises(SqlRejected):
            validate("with x as (select set_config('app.org_id','0'::text,true)) "
                     "select * from v_sales, x")

    def test_current_setting_probe(self):
        with self.assertRaises(SqlRejected):
            validate("select current_setting('app.org_id')")

    def test_comma_join_smuggles_second_table(self):
        # Old FROM/JOIN regex captured only the first identifier after FROM.
        with self.assertRaises(SqlRejected):
            validate("select * from v_sales, auth.users")

    def test_function_only_query_no_from(self):
        for sql in ("select version()", "select current_user",
                    "select inet_server_addr()", "select pg_sleep(10)",
                    "select txid_current()"):
            with self.subTest(sql=sql), self.assertRaises(SqlRejected):
                validate(sql)

    def test_base_tables_no_longer_allowed(self):
        # Allowlist narrowed to the five documented views.
        for t in ("sales", "customers", "employees", "purchases", "sale_items"):
            with self.subTest(table=t), self.assertRaises(SqlRejected):
                validate(f"select count(*) from {t}")


class TestStillRejectsTheObviousBad(unittest.TestCase):
    def test_not_a_select(self):
        for sql in ("insert into v_sales values(1)", "update v_sales set x=1",
                    "delete from v_sales", "drop table v_sales",
                    "grant select on v_sales to public"):
            with self.subTest(sql=sql), self.assertRaises(SqlRejected):
                validate(sql)

    def test_stacked_statement(self):
        with self.assertRaises(SqlRejected):
            validate("select * from v_sales; drop table v_sales")

    def test_pg_catalog(self):
        with self.assertRaises(SqlRejected):
            validate("select * from pg_catalog.pg_tables")

    def test_empty(self):
        for sql in ("", "   ", ";"):
            with self.subTest(sql=repr(sql)), self.assertRaises(SqlRejected):
                validate(sql)


class TestAdmitsLegitimateReporting(unittest.TestCase):
    """The queries the assistant must still be able to run."""

    def test_simple_aggregate(self):
        validate("select sum(total) from v_sales where status='completed'")

    def test_group_by_with_functions(self):
        validate("select date_trunc('month', sale_date) m, sum(total) rev "
                 "from v_sales group by 1 order by 1")

    def test_cte_over_allowed_view(self):
        validate("with monthly as (select sale_date, total from v_sales) "
                 "select count(*) from monthly, v_sales")

    def test_join_between_two_allowed_views(self):
        validate("select p.product, sum(l.line_total) "
                 "from v_sale_lines l join v_products p on p.product = l.product "
                 "group by 1")

    def test_semicolon_inside_string_literal_is_fine(self):
        validate("select product from v_products where product = 'a;b'")

    def test_window_function(self):
        validate("select product, row_number() over (order by cost desc) "
                 "from v_products")

    def test_all_five_views(self):
        for v in ("v_sales", "v_sale_lines", "v_inventory", "v_products", "v_purchases"):
            with self.subTest(view=v):
                validate(f"select count(*) from {v}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

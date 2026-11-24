"""Reading uploaded files by what they contain, not what they're called.

Run from api/:  python -m unittest app.cleaning.test_io
"""
import gzip
import io
import unittest

from openpyxl import Workbook

from app.cleaning import io as reader
from app.cleaning.fields import auto_map, detect_entity, guess_field
from app.cleaning.profile import line_total_share

CSV = "Invoice,Date,Item,Qty,Price\n1,2026-01-05,Zinger,2,3.250\n2,2026-01-06,Fries,1,1.750\n"


def xlsx(rows) -> bytes:
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ByContent(unittest.TestCase):
    def test_name_does_not_matter(self):
        for name in ("sales.csv", "export", "", "data.xlsx"):
            h, rows, _ = reader.read_table(name, CSV.encode())
            self.assertEqual(h, ["Invoice", "Date", "Item", "Qty", "Price"], name)
            self.assertEqual(len(rows), 2)

    def test_excel_named_csv_is_read_as_excel(self):
        data = xlsx([["Invoice", "Item", "Qty"], [1, "Zinger", 2]])
        h, rows, sheets = reader.read_table("sales.csv", data)
        self.assertEqual((h, rows), (["Invoice", "Item", "Qty"], [[1, "Zinger", 2]]))

    def test_gzipped_file_is_unpacked(self):
        h, rows, _ = reader.read_table("sales.csv", gzip.compress(CSV.encode()))
        self.assertEqual(len(rows), 2)
        h, rows, _ = reader.read_table("x", gzip.compress(xlsx([["A", "B"], [1, 2]])))
        self.assertEqual(rows, [[1, 2]])

    def test_gzip_bomb_is_refused(self):
        with self.assertRaises(reader.TooLarge):
            reader.gunzip(gzip.compress(b"a" * 2_000_000), limit=1_000_000)

    def test_excel_unicode_text_export(self):
        text = "الصنف\tالكمية\nزنجر\t2\nبطاطا\t1\n"
        h, rows, _ = reader.read_table("x.txt", text.encode("utf-16"))
        self.assertEqual(h, ["الصنف", "الكمية"])
        self.assertEqual(rows, [["زنجر", "2"], ["بطاطا", "1"]])

    def test_a_pdf_or_image_is_refused(self):
        for data in (b"%PDF-1.7 ...", b"\x89PNG\r\n\x1a\n...", b"abc\x00\x00def"):
            with self.assertRaises(ValueError):
                reader.read_table("sales.csv", data)


class NoSilentCut(unittest.TestCase):
    def test_too_many_rows_says_how_many(self):
        data = ("A,B\n" + "1,2\n" * 12).encode()
        with self.assertRaises(reader.TooManyRows) as cm:
            reader.read_table("x.csv", data, max_rows=10)
        self.assertEqual(cm.exception.rows, 12)
        h, rows, _ = reader.read_table("x.csv", data, max_rows=12)
        self.assertEqual(len(rows), 12)

    def test_preview_may_cut(self):
        data = ("A,B\n" + "1,2\n" * 50).encode()
        self.assertEqual(len(reader.read_table("x.csv", data, max_rows=10, cut=True)[1]), 10)

    def test_excel_too_many_rows(self):
        data = xlsx([["A", "B"]] + [[i, i] for i in range(15)])
        with self.assertRaises(reader.TooManyRows) as cm:
            reader.read_table("x.xlsx", data, max_rows=10)
        self.assertEqual(cm.exception.rows, 15)


class HeaderRow(unittest.TestCase):
    def test_file_without_header_keeps_its_first_row(self):
        data = "1001,2026-01-05,Zinger,2,3.250\n1002,2026-01-06,Fries,1,1.750\n1003,2026-01-06,Pepsi,3,0.500\n1004,2026-01-07,Wings,1,4.000\n"
        h, rows, _ = reader.read_table("x.csv", data.encode())
        self.assertEqual(h, ["Column 1", "Column 2", "Column 3", "Column 4", "Column 5"])
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0][2], "Zinger")

    def test_normal_header_is_a_header(self):
        h, rows, _ = reader.read_table("x.csv", CSV.encode())
        self.assertEqual(h[0], "Invoice")

    def test_unknown_header_names_are_still_a_header(self):
        data = "Ref,When,What,How many\n1,2026-01-05,Zinger,2\n2,2026-01-06,Fries,1\n3,2026-01-06,Tea,4\n"
        self.assertEqual(reader.read_table("x.csv", data.encode())[0][0], "Ref")

    def test_years_as_column_names_are_a_header(self):
        data = "Item,2024,2025\nZinger,100,120\nFries,80,95\nTea,40,52\n"
        self.assertEqual(reader.read_table("x.csv", data.encode())[0], ["Item", "2024", "2025"])


class WordsThatChangeTheMeaning(unittest.TestCase):
    def test_profit_is_not_the_total(self):
        self.assertEqual(guess_field("total_profit")[0], "profit")
        self.assertEqual(guess_field("Gross Margin")[0], "profit")

    def test_a_customer_id_is_not_a_name(self):
        for h in ("customer_id", "Customer Code", "كود الزبون", "branch code"):
            self.assertIsNone(guess_field(h)[0], h)

    def test_id_fields_keep_their_ids(self):
        self.assertEqual(guess_field("invoice id")[0], "invoice_number")
        self.assertEqual(guess_field("product code")[0], "sku")

    def test_a_percentage_is_not_an_amount_except_a_discount(self):
        self.assertIsNone(guess_field("tax percent")[0])
        self.assertEqual(guess_field("نسبة الخصم")[0], "discount")

    def test_a_mall_is_a_branch(self):
        self.assertEqual(guess_field("shopping_mall")[0], "branch")


class SalesByCategory(unittest.TestCase):
    H = ["invoice_no", "invoice_date", "customer_id", "category", "quantity", "selling_price_per_unit", "total_profit",
         "payment_method", "shopping_mall"]
    UNIT = {"Clothing": 300.08, "Shoes": 600.17, "Books": 15.15, "Toys": 35.84}
    QTY = [1, 3, 5, 2]

    def rows(self, line_total: bool):
        out = []
        for i in range(40):
            cat = list(self.UNIT)[i % 4]
            q = self.QTY[(i // 4) % 4]
            price = self.UNIT[cat] * (q if line_total else 1)
            out.append([f"I{i}", "10/30/2022 9:58", f"C{i}", cat, str(q), f"{price:.2f}", "5.0", "Cash", "Kanyon"])
        return out

    def test_line_totals_called_unit_price_are_read_as_totals(self):
        m = auto_map(self.H, self.rows(line_total=True))
        self.assertEqual(m["selling_price_per_unit"]["field"], "total")
        self.assertEqual(m["selling_price_per_unit"]["evidence"]["type"], "line_total")
        self.assertTrue(m["selling_price_per_unit"]["review"])
        self.assertEqual(m["total_profit"]["field"], "profit")
        self.assertIsNone(m["customer_id"]["field"])
        self.assertEqual(m["shopping_mall"]["field"], "branch")
        fields = {v["field"] for v in m.values() if v["field"]}
        self.assertEqual(detect_entity(fields, self.H), "sales")

    def test_real_unit_prices_stay_unit_prices(self):
        m = auto_map(self.H, self.rows(line_total=False))
        self.assertEqual(m["selling_price_per_unit"]["field"], "unit_price")
        self.assertEqual(line_total_share(self.rows(False), 5, 4, 3), 0.0)


if __name__ == "__main__":
    unittest.main()

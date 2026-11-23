"""One branch, one product, whatever the spelling or language.

Run from api/:  python -m unittest app.cleaning.test_duplicates

From a restaurant account that ended up with 30 branches for ~10 real ones
("Khalda", "خلدا", "خلده", "فرع خلدا") and every dish twice, in English and in
Arabic, each with half the sales.
"""

import unittest
from collections import Counter

from app.cleaning import engine
from app.cleaning.arabic import place_key
from app.cleaning.bilingual import pair, score
from app.cleaning.engine import Matcher, cluster_values


class Branches(unittest.TestCase):

    def test_every_spelling_of_a_place_is_one_key(self):
        for group in (["Khalda", "خلدا", "خلده", "فرع خلدا"], ["Aqaba", "عقبة", "فرع العقبة"],
                      ["Shmeisani", "شميساني", "فرع الشميساني"], ["Sweifieh", "الصويفية", "فرع الصويفية"],
                      ["Gardens", "جاردنز", "فرع الجاردنز"], ["Abdoun", "عبدون", "فرع عبدون"],
                      ["إربد الجامعة", "فرع إربد - شارع الجامعة"]):
            self.assertEqual(len({place_key(g) for g in group}), 1, group)

    def test_different_places_stay_apart(self):
        for a, b in (("Irbid", "إربد الجامعة"), ("عبدون", "عبدون - الدوار الأول"), ("خلدا", "Shmeisani"),
                     ("الفرع الرئيسي", "فرع صويلح")):
            self.assertNotEqual(place_key(a), place_key(b), (a, b))

    def test_cleaning_merges_branch_spellings(self):
        out = cluster_values(Counter({"فرع خلدا": 5, "Khalda": 3, "خلده": 1, "Shmeisani": 4}), "branch")
        self.assertEqual({out[v][0] for v in ("فرع خلدا", "Khalda", "خلده")}, {"فرع خلدا"})
        self.assertEqual(out["Shmeisani"][0], "Shmeisani")

    def test_bare_city_joins_its_only_branch_there(self):
        out = cluster_values(Counter({"فرع إربد - شارع الجامعة": 5, "Irbid": 3}), "branch")
        self.assertEqual(out["Irbid"][0], "فرع إربد - شارع الجامعة")

    def test_bare_city_with_two_branches_there_stays_apart(self):
        out = cluster_values(Counter({"فرع إربد - شارع الجامعة": 5, "Irbid Mecca Street": 4, "Irbid": 3}), "branch")
        self.assertEqual(out["Irbid"][0], "Irbid")

    def test_existing_branch_found_from_another_spelling(self):
        m = Matcher([{"name": "Khalda", "keys": ["Khalda", ""]}], loose=True, places=True)
        self.assertEqual(m.match("فرع خلدا")[0], "Khalda")


MENU_AR = {"ساندويش زنجر دجاج مقرمش": (3.25, "برجر وسناك"), "ماء معدني 0.5 لتر": (0.35, "مياه"),
           "سفن أب 330 مل": (0.5, "مشروبات غازية"), "بيبسي 330 مل": (0.5, "مشروبات غازية"),
           "بيبسي 1 لتر": (0.9, "مشروبات غازية"), "ساندويش شاورما دجاج سوبر": (2.25, "شاورما"),
           "نصف دجاجة عالفحم مع أرز ومقبلات": (4.5, "وجبات شرقية"), "وجبة فاهيتا دجاج مكسيكي": (4.5, "سناك غربي")}


class Products(unittest.TestCase):

    def test_english_and_arabic_names_of_one_dish_pair(self):
        got = pair({"Crispy Zinger Sandwich": (3.25, "برجر وسناك"), "Mineral Water 500ml": (0.35, "مياه"),
                    "7UP 330ml can": (0.5, "مشروبات غازية"), "Pepsi 330ml can": (0.5, "مشروبات غازية"),
                    "Half Grilled Chicken With Rice": (4.5, "وجبات شرقية")}, MENU_AR)
        self.assertEqual({k: v[0] for k, v in got.items()}, {
            "Crispy Zinger Sandwich": "ساندويش زنجر دجاج مقرمش", "Mineral Water 500ml": "ماء معدني 0.5 لتر",
            "7UP 330ml can": "سفن أب 330 مل", "Pepsi 330ml can": "بيبسي 330 مل",
            "Half Grilled Chicken With Rice": "نصف دجاجة عالفحم مع أرز ومقبلات"})

    def test_different_price_never_pairs(self):
        self.assertEqual(pair({"Crispy Zinger Sandwich": (2.25, None)}, MENU_AR), {})

    def test_different_category_never_pairs(self):
        self.assertEqual(pair({"Crispy Zinger Sandwich": (3.25, "حلويات")}, MENU_AR), {})

    def test_sizes_must_agree(self):
        self.assertEqual(score("Pepsi 1L", "بيبسي 330 مل"), 0.0)
        self.assertGreater(score("Pepsi 1L", "بيبسي 1 لتر"), 0)

    def test_same_price_different_dish_never_pairs(self):
        # Same price and category, different dish: fajita vs half chicken would need words in common.
        self.assertEqual(pair({"Fajita Chicken Meal": (4.5, "وجبات شرقية")}, MENU_AR), {})

    def test_engine_proposes_the_merge_for_review(self):
        h = ["Invoice No", "Date", "Item", "Category", "Qty", "Unit Price"]
        rows = [["1", "2026-01-05", "ساندويش زنجر دجاج مقرمش", "برجر وسناك", "1", "3.25"],
                ["2", "2026-01-05", "Crispy Zinger Sandwich", "برجر وسناك", "2", "3.25"],
                ["3", "2026-01-06", "Crispy Zinger Sandwich", "برجر وسناك", "1", "3250"]]
        m = {"Invoice No": "invoice_number", "Date": "date", "Item": "product", "Category": "category",
             "Qty": "quantity", "Unit Price": "unit_price"}
        res = engine.run(h, rows, m)
        merged = {(c["row"], c["new"]) for c in res["changes"] if c["rule"] == "product_match"}
        self.assertEqual(merged, {(1, "ساندويش زنجر دجاج مقرمش"), (2, "ساندويش زنجر دجاج مقرمش")})


if __name__ == "__main__":
    unittest.main()

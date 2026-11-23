"""Name matching for products and suppliers (cleaning/engine.py: Matcher, cluster_values).

Run from api/:  python -m unittest app.cleaning.test_matching

The negative cases are real merges a restaurant account ended up with: a
garlic sack and minced veal became "Mixed Grill 1kg", a carton of 500 paper
boxes became "Mineral Water 500ml", five different suppliers became "Al Najah
Food". One shared word ("al", "kg", "شاورما", "تجارة") was enough.
"""

import unittest
from collections import Counter

from app.cleaning.engine import Matcher, cluster_values

MENU = ["Coca-Cola 330ml", "Pepsi 330ml", "بيبسي 1 لتر", "زيت زيتون زياد 1 لتر", "Mixed Grill 1kg",
        "وجبة شاورما لحم عربي", "برجر لحم كلاسيك بلدي", "Mineral Water 500ml", "وجبة بروستد دجاج 4 قطع مقرمش",
        "دجاجة شواية كاملة مع أرز عائلي"]


def catalog(names):
    return Matcher([{"name": n, "keys": [n]} for n in names])


def same_group(values, kind="company"):
    out = cluster_values(Counter({v: 1 for v in values}), kind)
    return len({out[v][0] for v in values}) == 1


class Products(unittest.TestCase):
    m = catalog(MENU)

    def test_spelling_variants_still_match(self):
        self.assertEqual(self.m.match("coca cola 330")[0], "Coca-Cola 330ml")
        self.assertEqual(self.m.match("PEPSI 330ML")[0], "Pepsi 330ml")
        self.assertEqual(self.m.match("زيت زياد زيتون")[0], "زيت زيتون زياد 1 لتر")
        self.assertEqual(self.m.match("وجبة شاورما لحم عربي.")[0], "وجبة شاورما لحم عربي")

    def test_raw_materials_never_become_menu_items(self):
        for raw in ["ثوم مقشر صيني درجة أولى (كغ)", "لحم عجل مفروم محلي (كغ)", "صدور دجاج طازجة مبردة (كغ)",
                    "خبز شاورما صاج طازج", "خبز برجر سمسم جامبو", "صدور دجاج طازجة مبردة", "فروج دجاج كامل مفرغ",
                    "لحم خاروف روماني مبرد", "علب وجبات ورقية كرافت عائلي",
                    "علب وجبات ورقية كرافت عائلي (كرتونة (500 علبة))", "لحم عجل مفروم محلي"]:
            self.assertIsNone(self.m.match(raw)[0], raw)


class Suppliers(unittest.TestCase):

    def test_variants_of_one_supplier_merge(self):
        for group in (["AL MAHA DAIRY", "Al Maha Dairy Jordan"], ["TAYBEH POULTRY", "Taybeh Poultry Co"],
                      ["Modern Packaging Factory", "Modern Packaging"], ["Al Najah Food Supplies", "Al Najah Food"],
                      ["مؤسسة الرائد التجارية", "الرائد تجارة"], ["النجاح مواد غذائية", "مؤسسة النجاح للمواد الغذائية"]):
            self.assertTrue(same_group(group), group)

    def test_different_suppliers_stay_apart(self):
        for pair in (["Al Wafa Trading Co", "Al Najah Food"], ["AL RAED TRADING", "Al Najah Food"],
                     ["Al Quds Meat Est", "Al Maha Dairy Jordan"], ["Al Hikma Distribution", "Al Najah Food"],
                     ["شركة مزارع طيبة للدواجن", "شركة الزيوت النباتية الوطنية"], ["الوفاء تجارة", "الرائد تجارة"],
                     ["مؤسسة الحكمة للتوزيع", "مؤسسة النجاح للمواد الغذائية"],
                     ["مؤسسة ملحمة القدس لتجارة اللحوم", "مؤسسة سوق الخضار المركزي - عمان"],
                     ["الشركة الأردنية لمنتجات الألبان (المها)", "شركة الزيوت النباتية الوطنية"]):
            self.assertFalse(same_group(pair), pair)


if __name__ == "__main__":
    unittest.main()

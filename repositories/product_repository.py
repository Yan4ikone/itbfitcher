from pathlib import Path
from pprint import pformat

from dictionaries.dropdown_lists import DROPDOWN_LISTS
from dictionaries.products import PRODUCTS


class ProductRepository:

    def __init__(self):
        self.products = PRODUCTS
        self.search_index = {}
        self.rebuild_index()

    def all_products(self):
        return self.products.items()

    def add_alias(self, product, alias):

        info = self.get(product)

        if not info:
            return

        aliases = info.setdefault("aliases", [])

        if alias not in aliases:
            aliases.append(alias)

        self.rebuild_index()

    def add_score_word(self, product, word):

        info = self.get(product)

        if not info:
            return

        score_words = info.setdefault("score_words", [])

        if word not in score_words:
            score_words.append(word)
            self.rebuild_index()

    def add_material_code(self, product, material, code):

        info = self.get(product)

        if not info:
            return

        material_codes = info.setdefault(
            "material_codes",
            {}
        )

        material_codes[material] = code

    def add(self, product, info):

        self.products[product] = info
        self.rebuild_index()

    def update(self, product, info):

        self.products[product] = info
        self.rebuild_index()

    def remove(self, product):

        if product in self.products:
            del self.products[product]
            self.rebuild_index()

    def rebuild_index(self):

        self.search_index = {}

        for product, info in self.products.items():

            code = str(info.get("code", ""))
            self.search_index[product.lower()] = {
                "product": product,
                "code": code
            }

            for alias in info.get("aliases", []):

                self.search_index[alias.lower()] = {
                    "product": product,
                    "code": code
                }

    def find_product(self, description):

        if not description:
            return None

        return self.search_index.get(
            description.strip().lower()
        )

    def find_dropdown(self, description):

        description = (description or "").lower()

        for product, dropdown in DROPDOWN_LISTS.items():

            if product.lower() in description:
                return dropdown

        return None

    def all(self):
        return self.products.items()

    def get(self, product):
        return self.products.get(product)

    def has(self, product):
        return product in self.products

    def get_default_code(self, product):

        info = self.get(product)

        if not info:
            return ""

        return info.get("code", "")

    def get_material_code(self, product, material):

        info = self.get(product)

        if not info:
            return ""

        return info.get(
            "material_codes",
            {}
        ).get(
            material.lower(),
            ""
        )

    def get_material_codes(self, product):

        info = self.get(product)

        if not info:
            return {}

        return info.get("material_codes", {})

    def get_aliases(self, product):

        info = self.get(product)

        if not info:
            return []

        return info.get("aliases", [])

    def get_patterns(self, product):

        info = self.get(product)

        if not info:
            return []

        return info.get("patterns", [])

    def get_score_words(self, product):

        info = self.get(product)

        if not info:
            return []

        return info.get("score_words", [])

    def get_display_name(self, product):

        info = self.get(product)

        if not info:
            return product.capitalize()

        return info.get("display_name", product.capitalize())

    def save(self):

        path = Path(__file__).parent.parent / "dictionaries" / "products.py"

        with open(path, "w", encoding="utf-8") as f:

            f.write("PRODUCTS = ")
            f.write(pformat(self.products, width=140, sort_dicts=False))
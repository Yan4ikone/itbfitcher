from repositories.product_repository import ProductRepository
from dictionaries.dropdown_lists import DROPDOWN_LISTS


class LearningBuilder:

    def __init__(self):

        self.products = ProductRepository()

    # ==========================================================
    # PRODUCTS
    # ==========================================================

    def add_product(self, item):
        if self.products.has(item.description):
            return

        self.products.add(
            item.description,
            {
                "code": item.code,
                "patterns": [],
                "aliases": [],
                "material_codes": {}
            }
        )

    # ==========================================================
    # ALIASES
    # ==========================================================

    def add_alias(self, item):

        self.products.add_alias(
            item.product,
            item.alias
        )

    # ==========================================================
    # MATERIALS
    # ==========================================================

    def add_material(self, item):

        self.products.add_material_code(
            item.product,
            item.material,
            item.code
        )

    # ==========================================================
    # DROPDOWNS
    # ==========================================================

    def add_dropdown_variant(self, item):

        variants = DROPDOWN_LISTS.setdefault(
            item.product,
            []
        )

        code = str(item.code)

        if code not in variants:
            variants.append(code)

    # =====================================================
    # SAVE
    # =====================================================

    def save_products(self):
        self.products.save()

    def save_dropdowns(self):
        pass

    def save(self):
        self.save_products()
        self.save_dropdowns()

from learning.builder import LearningBuilder


class LearningApplier:

    def __init__(self):

        self.builder = LearningBuilder()

    def apply(self, products, aliases, materials, dropdowns, patterns=None, dropdown_candidates=None):
        self._apply_products(products)
        self._apply_aliases(aliases)
        self._apply_materials(materials)
        self._apply_dropdowns(dropdowns)

        if patterns:
            self._apply_patterns(patterns)

        if dropdown_candidates:
            self._apply_dropdown_candidates(dropdown_candidates)
        self.builder.save()

    # ==========================================================
    # PRODUCTS
    # ==========================================================
    def _apply_products(self, products):
        for item in products:
            if not item.selected:
                continue

            self.builder.add_product(item)
    # ==========================================================
    # ALIASES
    # ==========================================================
    def _apply_aliases(self, aliases):
        for item in aliases:
            if not item.selected:
                continue
            self.builder.add_alias(item)
    # ==========================================================
    # MATERIALS
    # ==========================================================
    def _apply_materials(self, materials):
        for item in materials:
            if not item.selected:
                continue
            self.builder.add_material(item)
    # ==========================================================
    # DROPDOWNS
    # ==========================================================
    def _apply_dropdowns(self, dropdowns):
        for item in dropdowns:
            if not item.selected:
                continue
            self.builder.add_dropdown_variant(item)
    # ==========================================================
    # PATTERNS
    # ==========================================================
    def _apply_patterns(self, patterns):
        for item in patterns:
            if not item.selected:
                continue
            self.builder.add_pattern(item)
    # ==========================================================
    # DROPDOWN CANDIDATES (новый dropdown для товара без него)
    # ==========================================================
    def _apply_dropdown_candidates(self, dropdown_candidates):
        for item in dropdown_candidates:
            if not item.selected:
                continue
            self.builder.create_dropdown(item)
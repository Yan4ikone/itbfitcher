from pathlib import Path
from pprint import pformat
import importlib

import dictionaries.products as products_dictionary
from dictionaries.products import PRODUCTS


class LearningBuilder:

    def __init__(self):

        self.products = PRODUCTS
    # ==========================================================
    # PRODUCTS
    # ==========================================================
    def add_product(self, item):

        if self.products.get(item.description):
            return

        self.products[item.description] = {
            "code": str(item.code),
            "patterns": [],
            "aliases": [],
            "material_codes": {},
        }
    # ==========================================================
    # ALIASES
    # ==========================================================
    def add_alias(self, item):

        product = self.products.get(item.product)

        if not product:
            return

        aliases = product.setdefault(
            "aliases",
            []
        )
        alias = str(item.alias).strip().lower()

        if not alias:
            return
        if alias in {
            str(value).strip().lower()
            for value in aliases
        }:
            return

        aliases.append(alias)
    # ==========================================================
    # MATERIALS
    # ==========================================================
    def add_material(self, item):

        product = self.products.get(item.product)

        if not product:
            return

        materials = product.setdefault(
            "material_codes",
            {}
        )

        material = str(item.material).strip().lower()

        if not material:
            return

        materials[material] = str(item.code)
    # ==========================================================
    # DROPDOWNS
    # ==========================================================
    def add_dropdown_variant(self, item):

        product = self.products.get(item.product)

        if not product:
            return

        dropdown = product.setdefault(
            "dropdown",
            {"title": "Выберите вариант", "variants": []}
        )
        variants = dropdown.setdefault(
            "variants",
            []
        )
        code = str(item.code).strip()

        if not code:
            return
        for variant in variants:
            if str(
                variant.get("code", "")
            ).strip() == code:
                return

        variants.append({
            "code": code,
            "name": getattr(item, "name", "") or "",
            "group": getattr(item, "group", "") or "other",
        })
    # ==========================================================
    # PATTERNS
    # ==========================================================
    def add_pattern(self, item):

        product = self.products.get(item.product)

        if not product:
            return

        patterns = product.setdefault("patterns", [])
        pattern = str(item.pattern).strip()

        if not pattern:
            return

        if pattern not in patterns:
            patterns.append(pattern)
    # ==========================================================
    # SAVE PRODUCTS
    # ==========================================================
    def save_products(self):

        path = (
            Path(__file__).parent.parent
            / "dictionaries"
            / "products.py"
        )
        importlib.invalidate_caches()
        fresh_module = importlib.reload(products_dictionary)
        current_on_disk = fresh_module.PRODUCTS

        merged = self._merge_products(current_on_disk, self.products)

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:
            f.write("PRODUCTS = ")
            f.write(
                pformat(
                    merged,
                    width=140,
                    sort_dicts=False
                )
            )

        self.products = merged

    @staticmethod
    def _merge_products(current, ours):

        merged = {
            product: dict(info)
            for product, info in current.items()
        }

        for product, info in ours.items():

            if product not in merged:
                merged[product] = info
                continue

            target = merged[product]

            for key in ("aliases", "patterns"):

                existing = list(target.get(key, []) or [])
                incoming = info.get(key, []) or []

                for value in incoming:
                    if value not in existing:
                        existing.append(value)

                target[key] = existing

            existing_materials = dict(
                target.get("material_codes", {}) or {}
            )
            existing_materials.update(
                info.get("material_codes", {}) or {}
            )
            target["material_codes"] = existing_materials

            incoming_dropdown = info.get("dropdown") or {}
            incoming_variants = incoming_dropdown.get("variants", []) or []

            if incoming_variants:

                target_dropdown = target.setdefault(
                    "dropdown",
                    {"title": incoming_dropdown.get("title", "Выберите вариант"), "variants": []}
                )
                target_variants = target_dropdown.setdefault("variants", [])
                known_codes = {
                    str(v.get("code", "")).strip()
                    for v in target_variants
                }

                for variant in incoming_variants:

                    variant_code = str(variant.get("code", "")).strip()

                    if variant_code and variant_code not in known_codes:
                        target_variants.append(variant)
                        known_codes.add(variant_code)

            if not target.get("code") and info.get("code"):
                target["code"] = info["code"]

        return merged
    # ==========================================================
    # SAVE
    # ==========================================================
    def save(self):

        self.save_products()
import re

from cleaner.product_extractor import ProductExtractor
from learning.name_normalizer import normalize_dictionary_name


class ProductNameResolver:

    def __init__(self):
        self.extractor = ProductExtractor()

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def resolve(self, card):

        variants = []
        self._add(variants, card.title, 100)
        self._add(variants, card.slug, 90)
        self._add(variants, card.cleaned_text, 80)
        self._add(variants, card.description, 60)

        for value in card.specs.values():
            self._add(variants, str(value), 70)

        for value in card.features.values():
            self._add(variants, str(value),40)

        for value in card.sections.values():
            self._add(variants, str(value),30)
        best = self._choose_best(variants)
        quantity = self._find_quantity(card)

        if quantity and quantity not in best:
            best = f"{best} {quantity}"

        return normalize_dictionary_name(best).lower()

    # ==========================================================
    # VARIANTS
    # ==========================================================

    def _add(self, variants, text, weight):

        if not text:
            return

        text = self.extractor.extract(text)

        if len(text) < 3:
            return

        variants.append(
            {
                "text": text,
                "weight": weight,
            }
        )

    # ==========================================================
    # BEST
    # ==========================================================

    def _choose_best(self, variants):

        if not variants:
            return ""

        variants.sort(
            key=lambda x: (
                x["weight"],
                len(x["text"])
            ),
            reverse=True,
        )

        return variants[0]["text"]

    # ==========================================================
    # QUANTITY
    # ==========================================================

    def _find_quantity(self, card):

        fields = [
            card.title,
            card.slug,
            card.description,
            card.cleaned_text,
        ]
        fields.extend(card.specs.values())
        patterns = [
            r"(\d+)\s*шт",
            r"(\d+)\s*штук",
            r"(\d+)\s*пары",
            r"(\d+)\s*пар",
            r"(\d+)\s*комплект",
            r"(\d+)\s*упаков",
            r"(\d+)\s*pcs",
            r"количество.*?(\d+)",
        ]

        for field in fields:

            if not field:
                continue

            text = str(field).lower()

            for pattern in patterns:

                m = re.search(pattern, text)

                if m:
                    return f"{m.group(1)} шт"

        return ""


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

        #
        # 1. Явные поля характеристик
        #

        priority_keys = (
            "Количество в комплекте",
            "Количество товара",
            "Количество",
            "Комплектация",
            "Комплект",
        )

        for key, value in card.specs.items():

            if not value:
                continue

            key_l = key.lower()

            if any(
                    x.lower() in key_l
                    for x in priority_keys
            ):
                text = str(value).lower()
                m = re.search(r"\b(\d+)\b", text)

                if m:
                    return f"{m.group(1)} шт"

        #
        # 2. Комплектация
        #

        complect = str(card.specs.get("Комплектация", "")).lower()

        if complect:

            patterns = [
                r"[-:]\s*(\d+)\s*шт",
                r"комплект\s+из\s+(\d+)",
                r"набор\s+из\s+(\d+)",
                r"(\d+)\s*шт",
            ]

            for pattern in patterns:
                m = re.search(pattern, complect)
                if m:
                    return f"{m.group(1)} шт"

        #
        # 3. Только безопасные конструкции
        #

        fields = [
            card.description,
            card.cleaned_text,
        ]

        patterns = [
            r"комплект\s+из\s+(\d+)\s*(?:шт|штук)?",
            r"набор\s+из\s+(\d+)\s*(?:шт|штук)?",
            r"в\s+упаковке\s+(\d+)",
            r"упаковка\s+(\d+)",
            r"количество\s+в\s+комплекте.*?(\d+)",
            r"количество\s+товара.*?(\d+)",
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


import re

from cleaner.product_cleaner import clean_text
from cleaner.product_extractor import ProductExtractor


class ProductParser:

    def __init__(self):
        self.extractor = ProductExtractor()

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def parse(self, card):

        texts = []

        if card.title:
            texts.append(card.title)
        if card.slug:
            texts.append(card.slug)
        if card.description:
            texts.append(card.description)
        if card.material:
            texts.append(card.material)
        if card.quantity:
            texts.append(card.quantity)
        for key, value in card.specs.items():
            if not value:
                continue

            texts.append(str(value))

        for section in card.sections.values():
            if isinstance(section, dict):
                for value in section.values():
                    if value:
                        texts.append(str(value))
            elif isinstance(section, list):
                for value in section:
                    if value:
                        texts.append(str(value))
            elif section:
                texts.append(str(section))
        for value in card.features.values():
            if value:
                texts.append(str(value))

        raw_text = " ".join(texts)
        cleaned, _, _ = clean_text(raw_text)
        print("\nRAW:")
        print(raw_text)
        print("\nCLEANED:")
        print(cleaned)
        product = self.extractor.extract(cleaned)
        print("\nEXTRACTED PRODUCT:")
        print(product)
        quantity = self._extract_quantity(raw_text)

        if quantity:
            product = f"{product} {quantity}"

        spec_values = []

        for value in card.specs.values():
            if value:
                spec_values.append(str(value).lower())
        for k, v in card.specs.items():
            print(f"   {k}: {v}")
        return {
            "title": card.title.lower(),
            "slug": card.slug.lower(),
            "description": cleaned.lower(),
            "cleaned_text": cleaned.lower(),
            "search_text": raw_text.lower(),
            "specs": spec_values,
            "material": getattr(card, "material", ""),
            "quantity": getattr(card, "quantity", ""),
            "specs_dict": {
                k: str(v).lower()
                for k, v in card.specs.items()
            },
            "tokens": set(raw_text.lower().split()),
            "product_name": product,
        }
    # ==========================================================
    # QUANTITY
    # ==========================================================
    def _extract_quantity(self, text):

        patterns = [
            r"(\d+)\s*шт",
            r"(\d+)\s*штук",
            r"комплект\s+из\s+(\d+)",
            r"набор\s+из\s+(\d+)",
            r"(\d+)\s*pcs",
            r"(\d+)\s*pieces",
            r"(\d+)\s*пар",
            r"(\d+)\s*пары",
        ]
        text = text.lower()

        for pattern in patterns:

            m = re.search(pattern, text)

            if m:
                return f"{m.group(1)} шт"
        return ""
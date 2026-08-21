from cleaner.product_extractor import ProductExtractor
from cleaner.product_variants import ProductVariants


class ProductCandidates:

    def __init__(self):

        self.extractor = ProductExtractor()
        self.variants = ProductVariants()

    def build(self, card):

        candidates = []
        self._append(
            candidates,
            card.clean_title,
            card.quantity,
            "TITLE",
            100,
        )
        self._append(
            candidates,
            card.clean_slug,
            card.quantity,
            "URL",
            90,
        )
        self._append(
            candidates,
            card.clean_description,
            card.quantity,
            "DESCRIPTION",
            70,
        )
        unique = {}

        for item in candidates:

            name = item["product"]

            if (
                name not in unique
                or item["weight"] > unique[name]["weight"]
            ):
                unique[name] = item
        result = sorted(
            unique.values(),
            key=lambda x: x["weight"],
            reverse=True,
        )
        card.product_candidates = result

        if result:

            card.cleaned_text = result[0]["product"]

        return card

    def _append(self, result, text, quantity, source, weight):

        if not text:
            return

        variants = self.variants.build(text, quantity)

        for variant in variants:
            result.append({
                "product": variant["product"],
                "source": source,
                "weight": weight + variant["weight"],
                "variant": variant["source"],
                "text": text,
            })
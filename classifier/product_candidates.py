from cleaner.product_extractor import ProductExtractor
from cleaner.product_variants import ProductVariants


class ProductCandidates:

    def __init__(self):

        self.extractor = ProductExtractor()
        self.variants = ProductVariants()

    def build(self, card):

        candidates = []
        # ==========================================================
        # TITLE
        # ==========================================================
        self._append(
            candidates,
            card.clean_title,
            card.quantity,
            "TITLE",
            100,
        )
        # ==========================================================
        # URL / SLUG
        # ==========================================================
        self._append(
            candidates,
            card.clean_slug,
            card.quantity,
            "URL",
            90,
        )
        # ==========================================================
        # DESCRIPTION
        # ==========================================================
        self._append(
            candidates,
            card.clean_description,
            card.quantity,
            "DESCRIPTION",
            70,
        )
        # ==========================================================
        # OZON CATEGORY / BREADCRUMBS
        #
        # Пока только добавляем категорию как отдельный источник.
        # ==========================================================

        breadcrumbs = getattr(card, "breadcrumbs", None)

        if breadcrumbs:

            if isinstance(breadcrumbs, (list, tuple)):
                category_text = " ".join(
                    str(item)
                    for item in breadcrumbs
                    if item
                )
            else:
                category_text = str(breadcrumbs)

            self._append(
                candidates,
                category_text,
                card.quantity,
                "CATEGORY",
                80,
            )
        # ==========================================================
        # UNIQUE CANDIDATES
        # ==========================================================
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
        print()
        print("=" * 80)
        print("PRODUCT CANDIDATES")
        print("=" * 80)
        for item in result:

            print(f" {item['source']:<12}"
                  f"weight={item['weight']:<4}"
                  f"product={item['product']!r}"
                  )
        print("=" * 80)
        print()
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
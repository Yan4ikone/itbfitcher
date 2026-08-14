from cleaner.product_extractor import ProductExtractor


class ProductVariants:

    def __init__(self):

        self.extractor = ProductExtractor()
    # ==========================================================
    # PUBLIC
    # ==========================================================
    def build(self, text, quantity=""):

        product = self.extractor.extract(text)

        if not product:
            return []

        variants = []

        self._add(
            variants,
            product,
            100,
            "BASE",
        )
        quantity = self._normalize_quantity(quantity)

        if quantity:

            self._add(
                variants,
                f"{product} {quantity}",
                95,
                "QUANTITY",
            )
        words = product.split()

        # последнее существительное

        if len(words) > 1:

            self._add(
                variants,
                words[-1],
                60,
                "LAST_WORD",
            )
            if quantity:

                self._add(
                    variants,
                    f"{words[-1]} {quantity}",
                    55,
                    "LAST_WORD_QUANTITY",
                )

        # убрать дубли


        unique = {}

        for item in variants:

            if (
                item["product"] not in unique
                or item["weight"] > unique[item["product"]]["weight"]
            ):
                unique[item["product"]] = item

        return list(unique.values())
    # ==========================================================
    # INTERNAL
    # ==========================================================
    def _normalize_quantity(self, quantity):

        quantity = str(quantity).strip()

        if not quantity:
            return ""
        if quantity.isdigit():
            return f"{quantity} шт"
        return quantity

    def _add(self, result, product, weight, source):

        if not product:
            return

        result.append({
            "product": product,
            "weight": weight,
            "source": source,
        })
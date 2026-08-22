class DropdownResolver:

    def __init__(self, repository=None):
        self.repository = repository

    # ==========================================================
    # PRODUCT
    # ==========================================================

    def resolve(self, product):

        if not product:
            return ""

        if self.repository is None:
            return ""

        info = self.repository.get(product)

        if not info:
            return ""

        variants = info.get("variants", [])

        if not variants:
            return ""

        return product

    # ==========================================================
    # RESOLVE CODE
    # ==========================================================

    def resolve_code(self, result, card):

        if self.repository is None:
            return

        data = self.repository.get(result.product)

        if not data:
            return

        variants = data.get("variants", [])

        if not variants:
            return

        text = self._build_text(result, card)

        for variant in variants:

            group = str(variant.get("group", "")).strip().lower()

            if not group:
                continue

            if self._contains(text, group):

                self._apply_variant(
                    result,
                    variant,
                    source="DROPDOWN",
                    confidence=90,
                    review=False,
                )
                return

        material = str(result.material or "").strip().lower()

        if material:
            for variant in variants:

                name = str(variant.get("name", "")).strip().lower()
                group = str(variant.get("group", "")).strip().lower()

                if material == name or (group and material == group):
                    result.code = variant["code"]
                    result.dropdown_group = variant.get("group", "")
                    result.source = "DROPDOWN_MATERIAL"
                    result.confidence = 95

                    return

        first = variants[0]
        result.code = first["code"]
        result.dropdown_group = first.get("group", "")
        result.review = True
        result.source = "DROPDOWN_FIRST"
        result.confidence = 60

        result.alternatives = {
            item["code"]: item["name"]
            for item in variants
        }
    # ==========================================================
    # APPLY VARIANT
    # ==========================================================
    def _apply_variant(
        self,
        result,
        variant,
        source,
        confidence,
        review,
    ):
        code = str(variant.get("code", "")).strip()

        if not code:
            return

        result.code = code
        result.dropdown_group = str(variant.get("group", "")).strip()
        result.dropdown = str(variant.get("name", "")).strip()
        result.source = source
        result.confidence = confidence
        result.review = review
    # ==========================================================
    # TEXT
    # ==========================================================
    def _build_text(self, result, card):

        parts = [
            getattr(card, "title", ""),
            getattr(card, "description", ""),
            getattr(card, "cleaned_text", ""),
            getattr(card, "slug", ""),
            getattr(card, "material", ""),
            getattr(result, "material", ""),
        ]
        specs = getattr(card, "specs", {}) or {}

        for key, value in specs.items():

            parts.append(str(key))
            parts.append(str(value))

        return " ".join(
            str(value)
            for value in parts
            if value
        ).lower()
    # ==========================================================
    # MATCH
    # ==========================================================
    def _contains(self, text, value):

        if not text or not value:
            return False

        value = value.lower().strip()

        if not value:
            return False
        return value in text
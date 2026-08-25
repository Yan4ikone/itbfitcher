from resolver.dropdown_axis_resolver import AXIS_RESOLVERS, get_axis_resolver

class DropdownResolver:

    DEFAULT_AXES = (
        "material_volume",
        "material",
        "gender",
        "purpose",
        "mechanism",
    )

    def __init__(self, repository=None):
        self.repository = repository


    def resolve(self, product):

        if not product:
            return ""
        if self.repository is None:
            return ""

        info = self.repository.get(product)

        if not info:
            return ""

        dropdown = info.get("dropdown") or {}
        variants = dropdown.get("variants", [])

        if not variants:
            return ""
        return product


    def resolve_code(self, result, card):

        if self.repository is None:
            return

        info = self.repository.get(result.product)

        if not info:
            return

        dropdown = info.get("dropdown") or {}
        variants = dropdown.get("variants", [])

        if not variants:
            return
        # --------------------------------------------------
        # 1. Оси (material / gender / purpose / mechanism / material_volume)
        # --------------------------------------------------
        variant = self._resolve_by_axis(dropdown, variants, card, result)

        if variant:
            self._apply_variant(
                result,
                variant,
                source="DROPDOWN",
                confidence=90,
                review=False,
            )
            return
        # --------------------------------------------------
        # 2. Fallback: ищем group прямо в тексте карточки
        # --------------------------------------------------
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
        # --------------------------------------------------
        # 3. Fallback: материал совпадает с name/group варианта
        # --------------------------------------------------
        material = str(result.material or "").strip().lower()

        if material:

            for variant in variants:

                name = str(variant.get("name", "")).strip().lower()
                group = str(variant.get("group", "")).strip().lower()

                if material == name or (group and material == group):

                    self._apply_variant(
                        result,
                        variant,
                        source="DROPDOWN_MATERIAL",
                        confidence=95,
                        review=False,
                    )
                    return
        # --------------------------------------------------
        # 4. Ничего не определили — берём первый вариант, ставим на проверку
        # --------------------------------------------------
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
    # AXIS DISPATCH
    # ==========================================================
    def _resolve_by_axis(self, dropdown, variants, card, result):
        """
        Если у dropdown указана конкретная "axis" - используем
        только её. Иначе пробуем оси по умолчанию по очереди,
        пока какая-то не вернёт вариант.
        """

        explicit_axis = dropdown.get("axis")

        if explicit_axis:

            resolver = get_axis_resolver(explicit_axis)

            return resolver.find(variants, card, result)

        for axis in self.DEFAULT_AXES:

            resolver = AXIS_RESOLVERS.get(axis)

            if not resolver:
                continue

            variant = resolver.find(variants, card, result)

            if variant:
                return variant

        return None
    # ==========================================================
    # APPLY VARIANT
    # ==========================================================
    def _apply_variant(self, result, variant, source, confidence, review):
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
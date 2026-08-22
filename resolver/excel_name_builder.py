import re


class ExcelNameBuilder:

    def _need_volume(self, card):

        text = " ".join([
            getattr(card, "title", ""),
            getattr(card, "description", ""),
            getattr(card, "slug", ""),
        ]).lower()

        keywords = [
            "духи",
            "парфюм",
            "парфюмерная вода",
            "туалетная вода",
            "одеколон",
            "ароматизатор",
            "эфирное масло",
            "диффузор",
        ]
        return any(x in text for x in keywords)

    def build(self, card, product):

        if not product:
            return ""

        parts = [product]

        if self._need_volume(card):
            volume = self._volume(card)
            if volume:
                parts.append(volume)

        quantity = self._quantity(card)
        if quantity:
            parts.append(quantity)

        return " ".join(parts)

    # =====================================================
    # QUANTITY
    # =====================================================

    def _quantity(self, card):

        q = str(getattr(card, "quantity", "")).strip().lower()

        if not q:
            return ""
        if "комплект" in q:
            return "комплект"
        if "набор" in q:
            return "набор"

        m = re.search(r"(\d+)", q)

        if not m:
            return ""

        count = int(m.group(1))

        if count == 1:
            return ""

        if "пар" in q or "пара" in q:

            if count % 10 == 1 and count % 100 != 11:
                word = "пара"
            elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
                word = "пары"
            else:
                word = "пар"
            return f"{count} {word}"
        return f"{count} шт"

    # =====================================================
    # VOLUME
    # =====================================================

    def _volume(self, card):

        volume = str(getattr(card, "volume", "") or "").strip()

        if volume:
            return volume

        specs = getattr(card, "specs", {}) or {}

        fields = [
            "Объем",
            "Объём",
            "Объем, мл",
            "Объём, мл",
            "Объем товара",
            "Объём товара",
        ]
        for field in fields:

            value = specs.get(field)

            if value:
                return value

        text = self._text(card)
        m = re.search(r"(\d+)\s?(мл|л)", text)

        if m:
            return f"{m.group(1)} {m.group(2)}"
        return ""

    # =====================================================
    # SIZE
    # =====================================================

    def _size(self, card):

        specs = getattr(card, "specs", {}) or {}
        fields = [
            "Размер",
            "Диаметр",
            "Длина",
            "Высота",
            "Ширина",
        ]
        for field in fields:

            value = specs.get(field)

            if value:
                return value

        text = self._text(card)
        patterns = [
            r"(\d+)\s?дюйм",
            r"(\d+)\s?(см|мм|м)",
        ]
        for pattern in patterns:

            m = re.search(pattern, text)

            if m:
                if len(m.groups()) == 1:
                    return f"{m.group(1)} дюймов"
                return f"{m.group(1)} {m.group(2)}"
        return ""

    # =====================================================
    # HELPERS
    # =====================================================

    def _text(self, card):

        return " ".join(
            filter(
                None,
                [
                    getattr(card, "title", ""),
                    getattr(card, "description", ""),
                    getattr(card, "cleaned_text", ""),
                ],
            )
        ).lower()

    def _number(self, value):

        m = re.search(r"\d+", str(value))

        if m:
            return m.group()
        return ""
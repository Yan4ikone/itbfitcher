import re


class DropdownAxisResolver:
    """
    Базовый интерфейс: по списку вариантов и карточке/результату
    находит подходящий вариант или None, если сигнала недостаточно.
    """

    def find(self, variants, card, result):
        raise NotImplementedError


class MaterialAxisResolver(DropdownAxisResolver):
    """
    Ось "материал" - сравниваем result.material
    (уже найденный MaterialResolver'ом) с name/group варианта.
    """

    def find(self, variants, card, result):

        material = str(result.material or "").strip().lower()

        if not material:
            return None

        for variant in variants:

            name = str(variant.get("name", "")).strip().lower()
            group = str(variant.get("group", "")).strip().lower()
            explicit = str(variant.get("material", "")).strip().lower()

            if material in (name, group, explicit) and material:
                return variant

        return None


class KeywordAxisResolver(DropdownAxisResolver):
    """
    Универсальная ось по ключевым словам в тексте карточки.
    Подходит для пола (муж/жен/дет), назначения (зип/пылесос),
    механизма (кнопочный/поворотный) - везде, где вариант
    отличается не материалом, а словами в названии/описании.

    Каждый вариант должен иметь список "match": [...] с ключевыми
    словами/фразами. Если у варианта нет "match" - он пропускается
    (не участвует в автоматическом определении, только в fallback).
    """

    def find(self, variants, card, result):

        text = self._text(card)

        if not text:
            return None

        for variant in variants:

            keywords = variant.get("match", [])

            for keyword in keywords:

                keyword = str(keyword).strip().lower()

                if not keyword:
                    continue

                pattern = r"(?<!\w)" + re.escape(keyword) + r"\w*"

                if re.search(pattern, text):
                    return variant

        return None

    def _text(self, card):

        parts = [
            getattr(card, "title", ""),
            getattr(card, "description", ""),
            getattr(card, "cleaned_text", ""),
        ]

        specs = getattr(card, "specs", {}) or {}

        for key, value in specs.items():
            parts.append(str(key))
            parts.append(str(value))

        return " ".join(
            str(part)
            for part in parts
            if part
        ).lower()


class MaterialVolumeAxisResolver(DropdownAxisResolver):
    """
    Составная ось: сначала сужаем варианты по материалу (если он
    известен), затем внутри них ищем подходящий по порогу объёма
    в литрах (min_volume_l / max_volume_l у варианта).

    Вариант без min_volume_l/max_volume_l считается подходящим по
    объёму всегда (порогов нет - значит не ограничен).
    """

    _VOLUME_RE = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*(мл|л)\b",
        re.IGNORECASE,
    )

    def find(self, variants, card, result):

        material = str(result.material or "").strip().lower()

        pool = variants

        if material:

            by_material = [
                v for v in variants
                if str(v.get("material", v.get("name", ""))).strip().lower() == material
            ]

            if by_material:
                pool = by_material

        volume_l = self._extract_volume_liters(card)

        if volume_l is None:
            # материал сузил варианты, но порог объёма неизвестен -
            # если после сужения остался ровно один вариант, это
            # уже однозначный ответ
            if material and len(pool) == 1:
                return pool[0]
            return None

        for variant in pool:

            min_v = variant.get("min_volume_l")
            max_v = variant.get("max_volume_l")

            if max_v is not None and volume_l >= float(max_v):
                continue

            if min_v is not None and volume_l < float(min_v):
                continue

            return variant

        return None

    def _extract_volume_liters(self, card):

        text = " ".join(
            filter(
                None,
                [
                    getattr(card, "title", ""),
                    getattr(card, "description", ""),
                    getattr(card, "cleaned_text", ""),
                ],
            )
        ).lower()

        specs = getattr(card, "specs", {}) or {}
        text += " " + " ".join(str(v) for v in specs.values())

        match = self._VOLUME_RE.search(text)

        if not match:
            return None

        value = float(match.group(1).replace(",", "."))
        unit = match.group(2)

        if unit == "мл":
            value = value / 1000.0

        return value
# --------------------------------------------------------------------
# Диспетчер: имя оси из DROPDOWN_LISTS -> резолвер
# --------------------------------------------------------------------
AXIS_RESOLVERS = {
    "material": MaterialAxisResolver(),
    "gender": KeywordAxisResolver(),
    "purpose": KeywordAxisResolver(),
    "mechanism": KeywordAxisResolver(),
    "material_volume": MaterialVolumeAxisResolver(),
}


def get_axis_resolver(axis):
    return AXIS_RESOLVERS.get(axis, AXIS_RESOLVERS["material"])
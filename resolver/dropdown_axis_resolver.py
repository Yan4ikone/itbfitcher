import re

from utils.gender_extractor import find_known_gender


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


class GenderAxisResolver(DropdownAxisResolver):
    """
    Ось "пол/возрастная группа" (муж/жен/дет).

    В отличие от материала, здесь не нужен product-специфичный словарь
    кодов вида material_codes: код уже прописан прямо в варианте
    dropdown'а (products.py), нужно только определить САМ ФАКТ пола -
    и для этого используется общий словарь GENDER_ALIASES
    (dictionaries/all_dictionaries.py), а не match-список внутри
    конкретного варианта (который почти всегда пуст и не покрывает
    реальные формулировки в карточках).

    Канонический факт ("male"/"female"/"child") сравнивается с полем
    "group" варианта - в products.py эти значения уже используются
    именно в таком виде.
    """

    def find(self, variants, card, result):

        text = self._text(card)

        if not text:
            return None

        gender = find_known_gender(text)

        if not gender:
            return None

        for variant in variants:

            group = str(variant.get("group", "")).strip().lower()
            explicit = str(variant.get("gender", "")).strip().lower()

            if gender in (group, explicit):
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


class KeywordAxisResolver(DropdownAxisResolver):
    """
    Универсальная ось по ключевым словам в тексте карточки.
    Подходит для назначения (зип/пылесос), механизма (кнопочный/
    поворотный) - везде, где вариант отличается не материалом и не
    полом, а product-специфичными словами в названии/описании,
    которые не имеют смысла в общем словаре (см. GenderAxisResolver
    для пола/возраста - там сигнал общий и переиспользуемый).

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
class ScoredKeywordAxisResolver(DropdownAxisResolver):
    """
    Для "зонтичных" категорий словаря, где вариант - это НЕ разные
    материалы/полы/механизмы одного и того же товара, а совершенно
    РАЗНЫЕ предметы с разными кодами (пример: "аксессуар для рыбалки"
    -> крючок / сетка / сачок / чехол; "аксессуар для пылесоса" ->
    щётка / мешок / фильтр / моторчик).

    В отличие от KeywordAxisResolver (первое совпадение ключевого
    слова где угодно в тексте - выигрывает), здесь для каждого
    варианта считается СУММА баллов за совпадения в РАЗНЫХ полях
    карточки (характеристики - самый весомый сигнал, заголовок,
    описание) плюс бонус за материал, и код проставляется только
    если у победителя достаточный счёт И достаточный отрыв от
    второго места. Иначе - как и с обычной классификацией
    (см. AMBIGUOUS в resolver/product_resolver.py) - карточка не
    получает случайный первый совпавший код, а уходит на ручную
    проверку (это разрулит следующий шаг resolve_code - fallback
    "первый вариант + review=True").

    Формат варианта в словаре:

        {
            "name": "Щётка для пылесоса",
            "code": "...",
            "match": ["щетка", "щётка", "насадка-щетка"],
            "materials": ["пластик"],   # необязательно - бонус к счёту,
                                        # если result.material совпал
        }

    Используется, когда у dropdown указана ось "keyword_score"
    (dropdown["axis"] = "keyword_score" в словаре продукта).
    """

    SPECS_WEIGHT = 200
    TITLE_WEIGHT = 150
    TEXT_WEIGHT = 80
    MATERIAL_BONUS = 100

    # Ниже этого счёта - сигнала недостаточно, не гадаем
    MIN_SCORE = 150
    # Отрыв от второго места, ниже которого решение неоднозначно
    MIN_GAP = 80

    def find(self, variants, card, result):

        scored = []

        for variant in variants:

            keywords = [
                str(k).strip().lower()
                for k in variant.get("match", [])
                if str(k).strip()
            ]

            if not keywords:
                # У варианта без ключевых слов нет шанса набрать очки -
                # он не участвует в автоматическом выборе этой осью.
                continue

            score = self._score_variant(variant, keywords, card, result)

            if score > 0:
                scored.append((score, variant))

        if not scored:
            return None

        scored.sort(key=lambda item: item[0], reverse=True)

        top_score, top_variant = scored[0]

        if top_score < self.MIN_SCORE:
            return None

        if len(scored) > 1:

            second_score = scored[1][0]

            if top_score - second_score < self.MIN_GAP:
                # Неоднозначно - например, в тексте упомянуты и
                # "щётка", и "фильтр" примерно с равным весом. Лучше
                # отдать на ручную проверку, чем гадать.
                return None

        return top_variant

    def _score_variant(self, variant, keywords, card, result):

        title = str(getattr(card, "title", "") or "").lower()
        description = str(getattr(card, "description", "") or "").lower()
        cleaned_text = str(getattr(card, "cleaned_text", "") or "").lower()

        specs = getattr(card, "specs", {}) or {}
        specs_text = " ".join(str(v) for v in specs.values()).lower()

        free_text = f"{description} {cleaned_text}"

        score = 0

        # Каждое поле даёт очки максимум один раз за вариант -
        # чтобы одно и то же слово, повторённое в тексте 5 раз, не
        # перевешивало вариант, реально подтверждённый характеристикой.
        matched_specs = False
        matched_title = False
        matched_text = False

        for keyword in keywords:

            pattern = r"(?<!\w)" + re.escape(keyword) + r"\w*"

            if not matched_specs and re.search(pattern, specs_text):
                score += self.SPECS_WEIGHT
                matched_specs = True

            if not matched_title and re.search(pattern, title):
                score += self.TITLE_WEIGHT
                matched_title = True

            if not matched_text and re.search(pattern, free_text):
                score += self.TEXT_WEIGHT
                matched_text = True

        materials = [
            str(m).strip().lower()
            for m in variant.get("materials", [])
        ]

        material = str(getattr(result, "material", "") or "").strip().lower()

        if materials and material and material in materials:
            score += self.MATERIAL_BONUS

        return score


# --------------------------------------------------------------------
# Диспетчер: имя оси из DROPDOWN_LISTS -> резолвер
# --------------------------------------------------------------------
AXIS_RESOLVERS = {
    "material": MaterialAxisResolver(),
    "gender": GenderAxisResolver(),
    "purpose": KeywordAxisResolver(),
    "mechanism": KeywordAxisResolver(),
    "material_volume": MaterialVolumeAxisResolver(),
    "keyword_score": ScoredKeywordAxisResolver(),
}


def get_axis_resolver(axis):
    return AXIS_RESOLVERS.get(axis, AXIS_RESOLVERS["material"])
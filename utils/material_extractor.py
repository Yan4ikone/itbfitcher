import re

from dictionaries.all_dictionaries import MATERIAL_ALIASES

# ==================================================================
# Единый источник извлечения "материала" из произвольного текста.
# Карточки, построенные через models/card_builder.py::build_from_excel()
# ==================================================================

_MATERIAL_PATTERNS = (
    r"материал\s*(?:верха)?\s*[:\-]\s*([^\n\r\.;]+)",
    r"состав\s*[:\-]\s*([^\n\r\.;]+)",
    r"изготовлен[ао]?\s+из\s+([^\n\r\.;]+)",
)

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _MATERIAL_PATTERNS]

# ------------------------------------------------------------------
# ВЕРХ vs СТЕЛЬКА/ПОДКЛАДКА/ПОДОШВА
#
# У обуви, сумок и т.п. в характеристиках часто отдельно указан
# материал ОСНОВНОЙ части (верх) и материал ВСПОМОГАТЕЛЬНОЙ части
# (стелька, подкладка, подошва, внутренняя отделка). Для классификации
# нас интересует только материал верха/основной части - иначе код
# может проставиться по материалу стельки, а не самого товара.
# Используется в двух местах, поэтому вынесено сюда как единый
# источник (resolver/material_resolver.py - для подбора кода при
# классификации, learning/analyzer.py - для вкладки "материалы" в
# обучении).
# ------------------------------------------------------------------
EXCLUDED_MATERIAL_KEY_SUBSTRINGS = (
    "стельк",
    "подкладк",
    "подошв",
    "внутренн",
    "фурнитур",
    "молни",
    "шнур",
    "утеплител",
)

# Те же самые слова, но для чистки СВОБОДНОГО текста (title/description/
# characteristics одной строкой, как это бывает в Excel-пути) - вырезаем
# сегмент от слова-маркера до ближайшего разделителя (запятая/точка/
# точка с запятой/конец строки), чтобы материал стельки не просочился
# в поиск через общий текст.
_EXCLUDED_SEGMENT_PATTERN = re.compile(
    r"(?:" + "|".join(EXCLUDED_MATERIAL_KEY_SUBSTRINGS) + r")[^,;.\n]*",
    re.IGNORECASE,
)


def is_excluded_material_key(key: str) -> bool:
    """True, если ключ характеристики относится к вспомогательной части
    товара (стелька/подкладка/подошва и т.п.), а не к основному материалу."""

    key_l = str(key or "").lower()
    return any(bad in key_l for bad in EXCLUDED_MATERIAL_KEY_SUBSTRINGS)


def strip_excluded_material_mentions(text: str) -> str:
    """Вырезает из свободного текста упоминания материала стельки/
    подкладки/подошвы, чтобы они не попадали в общий поиск материала."""

    if not text:
        return text

    return _EXCLUDED_SEGMENT_PATTERN.sub(" ", text)


# ------------------------------------------------------------------
# ИЗВЕСТНЫЕ МАТЕРИАЛЫ (единый источник для extract_material() ниже и
# learning.learning_filters.normalize_material - раньше этот список
# дублировался в обоих местах и грозил разъехаться).
# ------------------------------------------------------------------
_KNOWN_MATERIAL_WORDS = sorted(
    {
        alias.lower()
        for aliases in MATERIAL_ALIASES.values()
        for alias in aliases
    },
    key=len,
    reverse=True,
)


def find_known_material(text: str) -> str:
    """Ищет в СВОБОДНОМ тексте (без метки "материал:") любое известное
    слово-материал из справочника MATERIAL_ALIASES. Возвращает то, что
    встречается РАНЬШЕ ВСЕХ по тексту; при совпадении на одной позиции
    выбирает более длинное/специфичное ('искусственная кожа' вместо
    'кожа')."""

    if not text:
        return ""

    text = str(text).lower()

    best = None  # (start_pos, -length, word)

    for known in _KNOWN_MATERIAL_WORDS:
        match = re.search(rf"(?<!\w){re.escape(known)}(?!\w)", text)
        if match:
            candidate = (match.start(), -len(known), known)
            if best is None or candidate < best:
                best = candidate

    return best[2] if best else ""


def extract_material(text: str) -> str:
    """
    Ищет явное упоминание материала в свободном тексте
    (характеристики, описание - неважно). Возвращает найденное
    значение как есть (без нормализации к одному слову - для этого
    есть learning.learning_filters.normalize_material) либо "",
    если ничего не найдено.
    """

    if not text:
        return ""

    text = strip_excluded_material_mentions(str(text))

    for pattern in _COMPILED:

        match = pattern.search(text)

        if match:

            value = match.group(1).strip(" ,;.-\t")

            if value:
                # Найденное по метке значение - это ФАКТ-кандидат, а не
                # готовый материал
                known = find_known_material(value)
                if known:
                    return known

    # ФОЛБЭК: явной метки "материал:"/"состав:" нет (или значение под
    # меткой не подтвердилось словарём), но материал может быть просто
    # упомянут в тексте без метки - как часто бывает в заголовках
    # товаров
    return find_known_material(text)
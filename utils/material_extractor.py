import re


# Единый источник извлечения "материала" из произвольного текста.


_MATERIAL_PATTERNS = (
    r"материал\s*(?:верха)?\s*[:\-]\s*([^\n\r\.;]+)",
    r"состав\s*[:\-]\s*([^\n\r\.;]+)",
    r"изготовлен[ао]?\s+из\s+([^\n\r\.;]+)",
)

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _MATERIAL_PATTERNS]


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

    text = str(text)

    for pattern in _COMPILED:

        match = pattern.search(text)

        if match:

            value = match.group(1).strip(" ,;.-\t")

            if value:
                return value

    return ""
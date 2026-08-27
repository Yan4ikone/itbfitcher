import re

# ==================================================================
# Единый источник извлечения "материала" из произвольного текста.
# Раньше похожая regex-логика была только в
# parser/ozon_parser.py::OzonParser._extract_material() и работала
# ТОЛЬКО для карточек, пришедших через живой скрапинг Ozon.
# Карточки, построенные через models/card_builder.py::build_from_excel()
# (основной пакетный Excel-путь) материал вообще не извлекали -
# card.material оставался пустым, из-за чего LearningAnalyzer никогда
# не видел материал у таких товаров и new_material_codes был всегда 0.
# ==================================================================

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
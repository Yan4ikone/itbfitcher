"""
Общие хелперы для отображения dropdown-вариантов человеку
(Excel-комментарии, alternatives, ручной пикер и т.п.).

Начиная с сессии про упрощение схемы products.py, НОВЫЕ
dropdown-варианты хранят только code/group/match - "name" на
уровне варианта и "title" на уровне dropdown больше не пишутся,
это был чистый дубль/шаблонный мусор ("group": "металл" уже
достаточно, отдельное "name": "Металл" ничего не добавляет).

Для СТАРЫХ записей (у которых name всё ещё есть в products.py)
используется явный name, если он задан - миграция не обязательна,
чтение полностью обратно совместимо.
"""

from utils.material_extractor import MATERIAL_GROUP_EN

# group хранится по-английски у большинства товаров (metal/plastic/...),
# но для показа человеку удобнее по-русски - обратный перевод.
MATERIAL_GROUP_RU = {en: ru for ru, en in MATERIAL_GROUP_EN.items()}


def variant_display_name(variant: dict) -> str:
    """Человеко-читаемое имя варианта для UI/Excel. Предпочитает явный
    "name" (старые записи), затем "group" (новые записи), и только
    если group пуст или это общий placeholder "other" - падает на
    первое слово из "match" (актуально для авто-детектированных
    вариантов, где group ещё не привязан ни к одному известному
    факту)."""

    name = str(variant.get("name", "") or "").strip()

    if name:
        return name

    group = str(variant.get("group", "") or "").strip()

    if group and group.lower() != "other":

        display = MATERIAL_GROUP_RU.get(group.lower(), group)

        return display[:1].upper() + display[1:] if display else display

    match = variant.get("match") or ()

    if match:
        first = str(match[0]).strip()
        return first[:1].upper() + first[1:] if first else first

    if group:
        return group[:1].upper() + group[1:]

    return ""


def variant_color_key(variant: dict) -> str:
    """Ключ для поиска цвета в MATERIAL_COLORS (там ключи
    материалов - по-русски). Пробуем group (переведя на русский,
    если нужно), затем name как запасной вариант для старых
    записей."""

    group = str(variant.get("group", "") or "").strip().lower()

    if group:
        return MATERIAL_GROUP_RU.get(group, group)

    return str(variant.get("name", "") or "").strip().lower()

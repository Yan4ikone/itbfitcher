from openpyxl.comments import Comment
from openpyxl.styles import PatternFill

from dictionaries.all_dictionaries import MATERIAL_COLORS



def apply_result(ws, row, code_col, result):
    set_code(ws, row, code_col, result)
    set_comment(ws, row, code_col, result)
    set_color(ws, row, code_col, result)


def set_code(ws, row, code_col, result):
    cell = ws.cell(row=row, column=code_col)
    try:
        cell.value = int(result.code)
    except (ValueError, TypeError):
        cell.value = result.code


def set_comment(ws, row, code_col, result):
    if not result.review:
        return

    alternatives = result.alternatives or {}

    text = "\n".join(
        f"{code} — {name}"
        for code, name in alternatives.items()
    )

    ws.cell(row=row, column=code_col).comment = Comment(text, "Classifier")


def _get_color_group(result):
    """Возвращает наиболее точную группу для визуального цвета."""
    candidates = (
        getattr(result, "material_group", ""),
        getattr(result, "material", ""),
        getattr(result, "dropdown_group", ""),
        getattr(result, "dropdown", ""),
        getattr(result, "color", ""),
    )

    for value in candidates:
        if not value:
            continue

        value = str(value).strip().lower()

        # Сначала точное совпадение.
        if value in MATERIAL_COLORS:
            return value

        # Затем поиск названия группы внутри значения.
        # Это позволяет обработать, например, "мужская одежда" -> "муж".
        for group in MATERIAL_COLORS:
            if group in value:
                return group

    return None


def set_color(ws, row, code_col, result):
    group = _get_color_group(result)
    if not group:
        return

    color = MATERIAL_COLORS.get(group)
    if not color:
        return

    ws.cell(row=row, column=code_col).fill = PatternFill(
        fill_type="solid",
        fgColor=color,
    )
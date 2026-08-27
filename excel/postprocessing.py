from openpyxl.styles import PatternFill, Font

from dictionaries.all_dictionaries import ALLOWED_PREFIXES, RESTRICTED_PREFIXES, MATERIAL_COLORS


# Очень светлые фоны для статуса строки.
# Кодовая ячейка получает свой цвет отдельно из MATERIAL_COLORS.
RED_ROW_FILL = PatternFill(fill_type="solid", fgColor="FCE4E4")
GREEN_ROW_FILL = PatternFill(fill_type="solid", fgColor="E8F5E9")
WHITE_FILL = PatternFill(fill_type="solid", fgColor="FFFFFF")

RED_FONT = Font(color="C00000")
GREEN_FONT = Font(color="008000")
BLACK_FONT = Font(color="000000")


def _code(value):
    if value is None:
        return ""
    return str(value).strip().replace(" ", "")


def _is_allowed(code):
    return bool(code) and any(code.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def _is_restricted(code):
    return bool(code) and any(code.startswith(prefix) for prefix in RESTRICTED_PREFIXES)


def apply_visual_postprocessing(
    ws,
    code_col_idx,
    decision_col_idx=None,
    max_row=None,
):
    """
    Финальная визуальная обработка результата.

    Приоритет:
      1. пустой / 0 -> красная строка;
      2. разрешённое исключение (ALLOWED_PREFIXES) -> зелёная строка;
      3. запрещённый код (RESTRICTED_PREFIXES) -> красная строка;
      4. остальные валидные коды -> обычная строка.

    Цвет самой ячейки кода НЕ трогаем: его задаёт result_engine
    по материалу / полу / возрасту / группе из MATERIAL_COLORS.
    """
    limit = max_row if max_row else ws.max_row

    for row in range(2, limit + 1):
        code_cell = ws.cell(row=row, column=code_col_idx)
        code = _code(code_cell.value)

        if not code or code == "0":
            _paint_row(ws, row, RED_ROW_FILL, RED_FONT)
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Нельзя"
            continue

        # ALLOWED_PREFIXES имеют приоритет над широкими запрещёнными
        # префиксами. Например, 8708 является исключением внутри 87.
        if _is_allowed(code):
            _paint_row(ws, row, GREEN_ROW_FILL, GREEN_FONT)
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Можно"
            continue

        if _is_restricted(code):
            _paint_row(ws, row, RED_ROW_FILL, RED_FONT)
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Нельзя"
            continue

        _paint_row(ws, row, WHITE_FILL, BLACK_FONT)
        if decision_col_idx:
            ws.cell(row=row, column=decision_col_idx).value = "Можно"


def _paint_row(ws, row, fill, font):
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = fill
        cell.font = font

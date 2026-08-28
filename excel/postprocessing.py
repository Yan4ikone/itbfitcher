from openpyxl.styles import PatternFill, Font

from dictionaries.all_dictionaries import ALLOWED_PREFIXES, RESTRICTED_PREFIXES


RED_ROW_FILL = PatternFill(fill_type="solid", fgColor="FCE4E4")
GREEN_ROW_FILL = PatternFill(fill_type="solid", fgColor="E8F5E9")

RED_FONT = Font(color="C00000")
GREEN_FONT = Font(color="008000")


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
    Финальная визуальная обработка Excel.

    Пустой/0 и запрещённый код -> красная строка.
    ALLOWED_PREFIXES -> зелёная строка и имеют приоритет над RESTRICTED_PREFIXES.
    Остальные коды не перекрашиваются.

    Ячейка кода пропускается специально: её цвет задаётся result_engine
    по MATERIAL_COLORS и поэтому не должен быть затёрт цветом статуса строки.
    """
    limit = max_row if max_row else ws.max_row

    for row in range(2, limit + 1):
        code_cell = ws.cell(row=row, column=code_col_idx)
        code = _code(code_cell.value)

        if not code or code == "0":
            _paint_row(ws, row, RED_ROW_FILL, RED_FONT, code_col_idx)
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Нельзя"
            continue

        if _is_allowed(code):
            _paint_row(ws, row, GREEN_ROW_FILL, GREEN_FONT, code_col_idx)
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Можно"
            continue

        if _is_restricted(code):
            _paint_row(ws, row, RED_ROW_FILL, RED_FONT, code_col_idx)
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Нельзя"
            continue

        if decision_col_idx:
            ws.cell(row=row, column=decision_col_idx).value = "Можно"


def _paint_row(ws, row, fill, font, code_col_idx):
    for col in range(1, ws.max_column + 1):
        if col == code_col_idx:
            continue
        cell = ws.cell(row=row, column=col)
        cell.fill = fill
        cell.font = font
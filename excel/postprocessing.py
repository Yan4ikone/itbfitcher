from openpyxl.styles import PatternFill, Font
from copy import copy

from dictionaries.all_dictionaries import ALLOWED_PREFIXES, RESTRICTED_PREFIXES


RED_ROW_FILL = PatternFill(fill_type="solid", fgColor="FCE4E4")
GREEN_ROW_FILL = PatternFill(fill_type="solid", fgColor="E8F5E9")

RED_FONT = Font(color="C00000", bold=True)
GREEN_FONT = Font(color="008000", bold=True)


def _code(value):
    if value is None:
        return ""
    text = str(value).strip().replace(" ", "")
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _is_zero(code):
    return code in {"", "0"}


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
    """Final visual status pass over the already classified Excel sheet."""
    limit = min(max_row, ws.max_row) if max_row else ws.max_row

    for row in range(2, limit + 1):
        code_cell = ws.cell(row=row, column=code_col_idx)
        code = _code(code_cell.value)

        # Пустые строки после конца данных не трогаем.
        row_has_data = any(
            ws.cell(row=row, column=col).value not in (None, "")
            for col in range(1, ws.max_column + 1)
        )
        if not row_has_data:
            continue

        if _is_zero(code):
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
    # Цвет кода сохраняем: result_engine использует его для MATERIAL_COLORS.
    original_code_fill = copy(ws.cell(row=row, column=code_col_idx).fill)
    original_code_comment = ws.cell(row=row, column=code_col_idx).comment

    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = fill
        cell.font = font

    code_cell = ws.cell(row=row, column=code_col_idx)
    code_cell.fill = original_code_fill
    code_cell.comment = original_code_comment
from openpyxl.styles import PatternFill, Font
from copy import copy

from dictionaries.all_dictionaries import ALLOWED_PREFIXES, RESTRICTED_PREFIXES


RED_ROW_FILL = PatternFill(fill_type="solid", start_color="FFF2F2", end_color="FFF2F2", fgColor="FFF2F2")
GREEN_ROW_FILL = PatternFill(fill_type="solid", start_color="E8F5E9", end_color="E8F5E9", fgColor="E8F5E9")

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


def apply_visual_postprocessing(ws, code_col_idx, decision_col_idx=None, max_row=None, logger=None):
    """Final deterministic visual pass after all Excel transformations."""
    limit = min(max_row, ws.max_row) if max_row else ws.max_row
    stats = {"red": 0, "green": 0, "normal": 0, "zero": 0, "restricted": 0, "allowed": 0}

    for row in range(2, limit + 1):
        code_cell = ws.cell(row=row, column=code_col_idx)
        code = _code(code_cell.value)

        row_has_data = any(
            ws.cell(row=row, column=col).value not in (None, "")
            for col in range(1, ws.max_column + 1)
        )
        if not row_has_data:
            continue

        if _is_zero(code):
            _paint_row(ws, row, RED_ROW_FILL, RED_FONT)
            stats["red"] += 1
            stats["zero"] += 1
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Нельзя"
            continue

        if _is_allowed(code):
            _paint_row(ws, row, GREEN_ROW_FILL, GREEN_FONT)
            stats["green"] += 1
            stats["allowed"] += 1
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Можно"
            continue

        if _is_restricted(code):
            _paint_row(ws, row, RED_ROW_FILL, RED_FONT)
            stats["red"] += 1
            stats["restricted"] += 1
            if decision_col_idx:
                ws.cell(row=row, column=decision_col_idx).value = "Нельзя"
            continue

        stats["normal"] += 1
        if decision_col_idx:
            ws.cell(row=row, column=decision_col_idx).value = "Можно"

    if logger:
        logger(
            "Визуальная постобработка: "
            f"красных={stats['red']} (0={stats['zero']}, запрещённых={stats['restricted']}), "
            f"зелёных={stats['green']} (исключений={stats['allowed']}), "
            f"обычных={stats['normal']}"
        )
    return stats


def _paint_row(ws, row, fill, font):
    """Красим всю строку. Цвет кода НЕ восстанавливаем: статус 0/запрет должен быть виден."""
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = copy(fill)
        cell.font = copy(font)

from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from dictionaries.all_dictionaries import MATERIAL_COLORS



def apply_result(ws, row, code_col, result):
    set_code(ws, row, code_col, result)
    set_comment(ws, row, code_col, result)
    set_color(ws, row, code_col, result.material)

def set_code(ws, row, code_col, result):

    cell = ws.cell(
        row=row,
        column=code_col
    )
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

    ws.cell(
        row=row,
        column=code_col
    ).comment = Comment(text, "Classifier")


def set_color(ws, row, code_col, material_group):

    color = MATERIAL_COLORS.get(material_group)

    if not color:
        return

    ws.cell(row=row, column=code_col).fill = PatternFill("solid", fgColor=color)


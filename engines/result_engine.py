from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from dictionaries.all_dictionaries import MATERIAL_COLORS
from dictionaries.dropdown_lists import DROPDOWN_LISTS


def apply_result(ws, row, code_col, result):
    set_code(ws, row, code_col, result)
    set_dropdown(ws, row, code_col, result)
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

def set_dropdown(ws, row, code_col, result):

    data = DROPDOWN_LISTS.get(result.dropdown)
    if not data or not isinstance(data, dict):
        return

    variants = data.get("variants", [])
    if not variants:
        return

    codes = [str(item["code"]) for item in variants if "code" in item]
    if not codes:
        return

    prompt = "\n".join(f'{item["code"]} — {item["name"]}' for item in variants)
    formula = '"' + ",".join(codes) + '"'

    dv = DataValidation(type="list", formula1=formula, allow_blank=True)
    dv.promptTitle = data.get("title", "Выберите код")
    dv.prompt = prompt
    dv.showInputMessage = True

    cell = f"{get_column_letter(code_col)}{row}"
    for existing in list(ws.data_validations.dataValidation):
        if cell in existing.cells:
            ws.data_validations.dataValidation.remove(existing)

    dv.add(cell)
    ws.add_data_validation(dv)

    code_cell = ws.cell(row=row, column=code_col)
    if not code_cell.value:
        code_cell.value = int(codes[0])

def set_color(ws, row, code_col, material_group):

    color = MATERIAL_COLORS.get(material_group)

    if not color:
        return

    ws.cell(row=row, column=code_col).fill = PatternFill("solid", fgColor=color)


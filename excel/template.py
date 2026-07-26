import os
import sys


def _find_template_path():
    template_name = "Шаблон.xlsm"

    if hasattr(sys, 'argv') and sys.argv[0]:
        main_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        path = os.path.join(main_dir, template_name)
        if os.path.exists(path):
            return path

    current_dir = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        path = os.path.join(current_dir, template_name)
        if os.path.exists(path):
            return path
        parent = os.path.dirname(current_dir)
        if parent == current_dir: break
        current_dir = parent

    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), template_name)


TEMPLATE_PATH = _find_template_path()

def detect_template_structure(ws):
    has_codes_in_d = False
    for row in range(2, min(22, ws.max_row + 1)):
        cell_val = ws.cell(row=row, column=4).value  # D = 4
        if cell_val:
            val_str = str(cell_val).strip()
            if val_str.isdigit() and len(val_str) == 10:
                has_codes_in_d = True
                break

    if has_codes_in_d:
        return {
            "desc_col": 2,  # B - Описание (ВСЕГДА)
            "code_col": 3,  # C - Тнвэд (ВСЕГДА)
            "decision_col": 9,  # I - Решение 107 (смещено)
            "surname_col": 10,  # J - Фамилия (смещена)
            "shifted": True
        }
    else:
        return {
            "desc_col": 2,  # B - Описание (ВСЕГДА)
            "code_col": 3,  # C - Тнвэд (ВСЕГДА)
            "decision_col": 8,  # H - Решение 107
            "surname_col": 9,  # I - Фамилия
            "shifted": False
        }
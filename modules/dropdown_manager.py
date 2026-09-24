import os
import sys

from openpyxl.comments import Comment
from openpyxl.styles import PatternFill

from dictionaries.all_dictionaries import MATERIAL_COLORS
from utils.dropdown_helpers import variant_display_name, variant_color_key


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dictionaries.products import PRODUCTS
except ImportError:
    print("⚠️ Warning: products.py не найден, выпадающие списки не будут созданы")
    PRODUCTS = {}

from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.utils import get_column_letter



def generate_tnved_codes():
    """Список всех уникальных кодов ТН ВЭД из словаря - источник для
    общего (на весь столбец) выпадающего списка apply_dropdowns() ниже.

    Раньше коды собирались как int(code) - для кода, начинающегося с
    "0" (в ТН ВЭД такие реально есть, например группа 05), это молча
    теряло ведущий ноль (int("0503109000") == 503109000 - другое,
    неверное число) ещё на этапе построения самого списка-источника,
    то есть даже если куратор выбирал код именно из этого выпадающего
    списка, а не печатал руками, ноль всё равно исчезал. Теперь коды
    остаются строками (сортировка - по (длина, значение), чтобы
    10-значные ТН ВЭД коды сортировались как обычно, а не лексикографи-
    чески вперемешку с более короткими значениями, если такие когда-
    нибудь попадутся) - число ведущих нулей сохраняется, а
    apply_dropdowns() ниже дополнительно ставит текстовый формат ('@')
    на сам список-источник, чтобы Excel не переинтерпретировал такую
    строку обратно в число при отображении."""

    if not PRODUCTS:
        return []

    unique_codes = set()

    def _add(code_value):
        code = str(code_value).strip()
        if code and code.isdigit() and code != "0":
            unique_codes.add(code)

    for name, info in PRODUCTS.items():
        if not isinstance(info, dict):
            continue

        code = ""
        for k, v in info.items():
            if "code" in str(k).lower() and "material" not in str(k).lower():
                code = str(v).strip()
                break

        _add(code)

        for mk, mv in info.items():
            if (
                    "material" in str(mk).lower()
                    and isinstance(mv, dict)
            ):
                for material, mat_code in mv.items():
                    _add(mat_code)
            if mk == "dropdown" and isinstance(mv, dict):
                for variant in mv.get("variants", []):
                    if not isinstance(variant, dict):
                        continue

                    _add(variant.get("code", ""))

    return sorted(unique_codes, key=lambda c: (len(c), c))


def apply_specific_dropdowns(
        ws,
        desc_col_idx,
        code_col_idx,
        max_row=None
):
    """
    Выпадающие списки берутся непосредственно из PRODUCTS.
    PRODUCTS[product]["dropdown"]:
    """

    if not PRODUCTS:
        return

    limit = max_row if max_row else ws.max_row

    for row in range(2, limit + 1):

        prod_cell = ws.cell(
            row=row,
            column=desc_col_idx
        )

        if not prod_cell.value:
            continue

        prod_name = str(
            prod_cell.value
        ).strip().lower()

        # --------------------------------------------------
        # Ищем товар в PRODUCTS
        # --------------------------------------------------

        product_info = None

        for product_name, info in PRODUCTS.items():

            if not isinstance(info, dict):
                continue

            if str(product_name).strip().lower() in prod_name:
                product_info = info
                break

        if not product_info:
            continue

        dropdown = product_info.get(
            "dropdown"
        )

        if not isinstance(dropdown, dict):
            continue

        variants = dropdown.get(
            "variants",
            []
        )

        if not variants:
            continue

        # --------------------------------------------------
        # Коды
        # --------------------------------------------------

        codes = []

        for item in variants:

            if not isinstance(item, dict):
                continue

            code = str(
                item.get("code", "")
            ).strip()

            if code and code not in codes:
                codes.append(code)

        if not codes:
            continue

        # --------------------------------------------------
        # Не трогаем ячейку, для которой уже построен свой,
        # более специфичный комментарий с вариантами - например,
        # result.alternatives для СПОРНОГО (result.review) кода
        # (см. processors/ozon_auto_processor.py::apply_result(),
        # engines/result_engine.py::set_comment()) или историческое
        # предупреждение (excel/writer.py::add_history_warning()).
        # Без этой проверки комментарий/DataValidation ниже молча
        # ЗАТЁРЛИ бы уже поставленный - тот источник иногда точнее
        # (например, при неоднозначности между НЕСКОЛЬКИМИ разными
        # товарами, а не только вариантами одного).
        # --------------------------------------------------
        cell = ws.cell(
            row=row,
            column=code_col_idx
        )

        if cell.comment is not None:
            continue

        # --------------------------------------------------
        # DataValidation
        # --------------------------------------------------

        formula = '"' + ",".join(codes) + '"'

        dv = DataValidation(
            type="list",
            formula1=formula,
            allow_blank=True
        )

        dv.prompt = dropdown.get(
            "title",
            "Выберите вариант"
        )

        dv.showInputMessage = True

        dv.add(cell)
        ws.add_data_validation(dv)

        # --------------------------------------------------
        # Комментарий
        # --------------------------------------------------

        comment_lines = []

        for item in variants:

            if not isinstance(item, dict):
                continue

            code = str(
                item.get("code", "")
            ).strip()

            display = variant_display_name(item)

            group = str(
                item.get("group", "")
            ).strip()

            if not code:
                continue

            if display and group and display.lower() != group.lower():
                comment_lines.append(
                    f"{code} - {display} ({group})"
                )
            elif display:
                comment_lines.append(
                    f"{code} - {display}"
                )
            else:
                comment_lines.append(
                    code
                )

        if comment_lines:

            cell.comment = Comment(
                "\n".join(comment_lines),
                "Classifier"
            )

        # --------------------------------------------------
        # Цвет
        #
        # Оставляем старую логику для случаев,
        # когда dropdown фактически представляет
        # один материал.
        # --------------------------------------------------

        materials = set()

        for item in variants:

            if not isinstance(item, dict):
                continue

            key = variant_color_key(item)

            if key:
                materials.add(key)

        if len(materials) == 1:

            material = next(
                iter(materials)
            )

            color = MATERIAL_COLORS.get(
                material
            )

            if color:

                cell.fill = PatternFill(
                    fill_type="solid",
                    fgColor=color
                )


def apply_dropdowns(wb, ws):
    tnved_codes = generate_tnved_codes()
    if not tnved_codes:
        return

    hidden_sheet_name = "DropdownData"
    if hidden_sheet_name in wb.sheetnames:
        del wb[hidden_sheet_name]

    hidden_ws = wb.create_sheet(hidden_sheet_name)
    hidden_ws.sheet_state = 'hidden'
    header = [str(cell.value).strip().lower() if cell.value else "" for cell in ws[1]]
    code_col_idx = None
    for idx, col_name in enumerate(header, start=1):
        if "тнвэд" in col_name or "код" in col_name:
            code_col_idx = idx
            break

    if not code_col_idx:
        return

    hidden_ws.cell(row=1, column=1, value="ТН ВЭД Коды")
    for row_idx, code in enumerate(tnved_codes, start=2):
        # code - строка (см. generate_tnved_codes выше) - пишем как
        # текст и явно ставим текстовый формат, чтобы ведущий ноль
        # (если есть) не потерялся и не потерялся бы повторно, если
        # кто-то откроет и пересохранит этот скрытый лист в Excel.
        cell = hidden_ws.cell(row=row_idx, column=1, value=code)
        cell.number_format = "@"
    safe_name = "List_TNVED_Codes"
    last_row = len(tnved_codes) + 1
    ref = f"'{hidden_sheet_name}'!$A$2:$A${last_row}"

    if safe_name in wb.defined_names:
        del wb.defined_names[safe_name]

    defn = DefinedName(safe_name, attr_text=ref)
    wb.defined_names.add(defn)
    dv = DataValidation(
        type="list",
        formula1=f"={safe_name}",
        allow_blank=True
    )
    dv.error = "Выберите код ТН ВЭД из списка"
    dv.errorTitle = "Неверный код"
    dv.prompt = "Выберите код из списка или введите вручную"
    dv.promptTitle = "Код ТН ВЭД"
    col_letter = get_column_letter(code_col_idx)
    dv.add(f"{col_letter}2:{col_letter}10000")
    ws.add_data_validation(dv)


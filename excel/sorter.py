from copy import copy

from openpyxl.comments import Comment
from openpyxl.formula.translate import Translator
from openpyxl.styles import Alignment, Border, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# "Пустой"/дефолтный стиль - используется, чтобы ЯВНО сбросить
# форматирование ячейки, у которой в исходных данных стиля не было
# (has_style=False), а не просто пропустить присвоение. Раньше (см.
# sort_by_description ниже) `if cell_data["font"]: cell.font = ...`
# при отсутствии стиля у ИСХОДНОЙ строки молча оставлял в ЦЕЛЕВОЙ
# ячейке то форматирование/комментарий/dropdown, что там было ДО
# сортировки (от другой строки, физически занимавшей эту позицию) -
# то есть, например, красная заливка "требует проверки" или
# текстовый формат '@' от чужого, уже не того кода могли молча
# "прилипнуть" к новой строке. См. products-dict-gradation-audit.md.
_DEFAULT_FONT = Font()
_DEFAULT_FILL = PatternFill()
_DEFAULT_ALIGNMENT = Alignment()
_DEFAULT_BORDER = Border()


def _index_single_cell_data_validations(ws):
    """{координата_ячейки: dv} для ОДНОклеточных DataValidation листа.

    Все per-строчные выпадающие списки результата классификации
    (engines/result_engine.py::set_dropdown, ozon_auto_processor.py -
    аналогичный код, modules/dropdown_manager.py::
    apply_specific_dropdowns) создают ОТДЕЛЬНЫЙ DataValidation на
    КАЖДУЮ строку и вызывают dv.add(cell) РОВНО один раз - то есть
    dv.sqref у каждого из них покрывает ровно одну ячейку. Именно
    поэтому их можно надёжно проиндексировать по координате и затем
    перенести на новую позицию при сортировке (см. sort_by_description
    ниже) - находка из products-dict-gradation-audit.md: раньше
    sort_by_description переставлял ЗНАЧЕНИЯ и базовое форматирование
    (шрифт/заливка/рамка/number_format) ячеек, но НЕ комментарии и НЕ
    DataValidation - те оставались привязаны к СТАРЫМ координатам, то
    есть после сортировки выпадающий список/подсказка с вариантами
    оказывались у ДРУГОЙ, уже не той строки. Многоклеточные dv (если
    когда-то появятся - например, общий список ТН ВЭД кодов на весь
    столбец из modules/dropdown_manager.py::apply_dropdowns) намеренно
    не индексируются и не трогаются - у них проблема сортировки не
    возникает (они и так покрывают весь диапазон одним правилом)."""

    index = {}

    for dv in list(ws.data_validations.dataValidation):

        ranges = list(dv.sqref.ranges)

        if len(ranges) != 1:
            continue

        cell_range = ranges[0]

        if (
            cell_range.min_row != cell_range.max_row
            or cell_range.min_col != cell_range.max_col
        ):
            continue

        coord = f"{get_column_letter(cell_range.min_col)}{cell_range.min_row}"
        index[coord] = dv

    return index


def _clone_data_validation(dv):
    """Копия DataValidation БЕЗ уже привязанных координат (sqref) -
    dv.add(cell) на новую ячейку добавляется отдельно вызывающим
    кодом. Нельзя просто переиспользовать исходный объект на новой
    координате - copy.copy(dv) делит общий sqref с оригиналом, а
    исходный dv к этому моменту ещё числится в ws.data_validations
    (удаляется отдельно, см. sort_by_description)."""

    return DataValidation(
        type=dv.type,
        formula1=dv.formula1,
        formula2=dv.formula2,
        allow_blank=dv.allow_blank,
        showDropDown=dv.showDropDown,
        showInputMessage=dv.showInputMessage,
        showErrorMessage=dv.showErrorMessage,
        prompt=dv.prompt,
        promptTitle=dv.promptTitle,
        error=dv.error,
        errorTitle=dv.errorTitle,
        operator=dv.operator,
    )


def sort_by_description(ws, desc_col_idx, last_row):

    dv_index = _index_single_cell_data_validations(ws)

    rows_data = []
    for row in range(2, last_row + 1):
        desc_value = ws.cell(row=row, column=desc_col_idx).value
        if not desc_value:
            continue
        row_cells = []
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=row, column=col)
            comment = cell.comment
            dv = dv_index.get(cell.coordinate)
            row_cells.append({
                "coordinate": cell.coordinate,
                "value": cell.value,
                "font": copy(cell.font) if cell.has_style else None,
                "fill": copy(cell.fill) if cell.has_style else None,
                "alignment": copy(cell.alignment) if cell.has_style else None,
                "border": copy(cell.border) if cell.has_style else None,
                "number_format": cell.number_format if cell.has_style else None,
                "comment_text": comment.text if comment else None,
                "comment_author": comment.author if comment else None,
                "dv": dv,
            })
        rows_data.append(row_cells)

    if not rows_data:
        return

    desc_idx = desc_col_idx - 1
    rows_data.sort(key=lambda r: str(r[desc_idx]["value"] or "").lower())

    # Старые однoклеточные DataValidation больше не нужны на своих
    # прежних координатах - убираем ИХ ВСЕ разом сейчас (а не по мере
    # переноса ниже), иначе к концу переноса на одной и той же ячейке
    # могли бы одновременно оказаться и старое (ещё не удалённое), и
    # новое правило.
    for dv in dv_index.values():
        try:
            ws.data_validations.dataValidation.remove(dv)
        except ValueError:
            pass

    # Перезаписываем строки в отсортированном порядке
    for new_row_idx, row_cells in enumerate(rows_data, start=2):
        for col_idx, cell_data in enumerate(row_cells, start=1):
            cell = ws.cell(row=new_row_idx, column=col_idx)
            value = cell_data["value"]

            if isinstance(value, str) and value.startswith("="):
                try:
                    value = Translator(
                        value,
                        origin=cell_data["coordinate"]
                    ).translate_formula(
                        cell.coordinate
                    )
                except Exception:
                    pass
            cell.value = value
            # Стиль/формат/комментарий - ВСЕГДА присваиваем явно (а не
            # только когда у исходной строки он был), иначе на месте
            # этой ячейки может остаться чужое форматирование от
            # строки, ФИЗИЧЕСКИ стоявшей здесь до сортировки.
            cell.font = cell_data["font"] or _DEFAULT_FONT
            cell.fill = cell_data["fill"] or _DEFAULT_FILL
            cell.alignment = cell_data["alignment"] or _DEFAULT_ALIGNMENT
            cell.border = cell_data["border"] or _DEFAULT_BORDER
            cell.number_format = cell_data["number_format"] or "General"

            cell.comment = (
                Comment(
                    cell_data["comment_text"],
                    cell_data["comment_author"] or "Classifier",
                )
                if cell_data["comment_text"]
                else None
            )

            old_dv = cell_data["dv"]
            if old_dv is not None:
                new_dv = _clone_data_validation(old_dv)
                new_dv.add(cell)
                ws.add_data_validation(new_dv)

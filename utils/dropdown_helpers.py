"""
Общие хелперы для отображения dropdown-вариантов человеку
(Excel-комментарии, alternatives, ручной пикер и т.п.).

Начиная с сессии про упрощение схемы products.py, НОВЫЕ
dropdown-варианты хранят только code/group/match - "name" на
уровне варианта и "title" на уровне dropdown больше не пишутся,
это был чистый дубль/шаблонный мусор ("group": "металл" уже
достаточно, отдельное "name": "Металл" ничего не добавляет).

Для СТАРЫХ записей (у которых name всё ещё есть в products.py)
используется явный name, если он задан - миграция не обязательна,
чтение полностью обратно совместимо.
"""

from openpyxl.worksheet.datavalidation import DataValidation

from utils.material_extractor import MATERIAL_GROUP_EN


def write_code_cell(cell, code):
    """Пишет код ТН ВЭД в ячейку, сохраняя ведущий ноль.

    Раньше во всех местах, где код пишется в ячейку (engines/
    result_engine.py::set_code, processors/ozon_auto_processor.py::
    apply_result/apply_cached_result), использовалось голое
    int(code) - для подавляющего большинства кодов это просто число,
    но код, начинающийся с "0" (такие коды в ТН ВЭД РЕАЛЬНО
    встречаются - например товарные позиции группы 05), при этом
    МОЛЧА терял этот ноль (int("0503109000") == 503109000 - код
    "укорачивается" и становится другим, неверным числом), да ещё и
    сама ячейка получала обычный числовой формат, из-за чего даже
    заново введённый вручную код с нулём в начале Excel по умолчанию
    отобразил бы без него. Жалоба Яна (products-dict-gradation-audit.md).

    Теперь: если код начинается с "0" - пишем его КАК ТЕКСТ и
    принудительно ставим текстовый формат ячейки ('@'), иначе
    сохраняем прежнее поведение (обычное число, если это вообще
    число - для сортировки/фильтрации в Excel так удобнее).

    Пустой код (result.code == "") - тоже прежнее поведение: пишем
    как есть (пустую строку), НЕ заменяем на None - вызывающий код
    (например, отдельная явная очистка C{row}=None у result.review в
    processors/ozon_auto_processor.py) сам решает, когда ячейку нужно
    именно обнулить. code is None - тоже прежнее поведение (пишем
    None как есть, а не строку "None")."""

    if code is None:
        cell.value = None
        return

    code = str(code).strip()

    if not code:
        cell.value = code
        return

    if code.startswith("0") and code.isdigit() and code != "0":
        cell.value = code
        cell.number_format = "@"
        return

    try:
        cell.value = int(code)
    except (ValueError, TypeError):
        cell.value = code


# group хранится по-английски у большинства товаров (metal/plastic/...),
# но для показа человеку удобнее по-русски - обратный перевод.
MATERIAL_GROUP_RU = {en: ru for ru, en in MATERIAL_GROUP_EN.items()}


def variant_display_name(variant: dict) -> str:
    """Человеко-читаемое имя варианта для UI/Excel. Предпочитает явный
    "name" (старые записи), затем "group" (новые записи), и только
    если group пуст или это общий placeholder "other" - падает на
    первое слово из "match" (актуально для авто-детектированных
    вариантов, где group ещё не привязан ни к одному известному
    факту)."""

    name = str(variant.get("name", "") or "").strip()

    if name:
        return name

    group = str(variant.get("group", "") or "").strip()

    if group and group.lower() != "other":

        display = MATERIAL_GROUP_RU.get(group.lower(), group)

        return display[:1].upper() + display[1:] if display else display

    match = variant.get("match") or ()

    if match:
        first = str(match[0]).strip()
        return first[:1].upper() + first[1:] if first else first

    if group:
        return group[:1].upper() + group[1:]

    return ""


def group_color_key(group: str) -> str:
    """Ключ для поиска цвета в MATERIAL_COLORS (там ключи материалов -
    по-русски) по голому значению факта ("group" варианта, или то же
    самое значение, уже записанное в отдельную колонку Excel -
    см. excel/postprocessing.py::apply_group_colors). Переводит с
    английского на русский, если нужно (group хранится по-английски
    у большинства товаров - metal/plastic/...)."""

    group = str(group or "").strip().lower()

    if not group:
        return ""

    return MATERIAL_GROUP_RU.get(group, group)


def variant_color_key(variant: dict) -> str:
    """Ключ для поиска цвета в MATERIAL_COLORS - пробуем group,
    затем name как запасной вариант для старых записей."""

    group = str(variant.get("group", "") or "").strip().lower()

    if group:
        return group_color_key(group)

    return str(variant.get("name", "") or "").strip().lower()


def build_alternatives_validation(codes, prompt="Выберите код вручную"):
    """Настоящий выпадающий список Excel (Data Validation, type="list")
    для набора кодов-альтернатив - используется и для result.alternatives
    (см. resolver/dropdown_resolver.py, случай "ничего не определили" /
    resolver/product_resolver.py, неоднозначность между несколькими
    товарами), и в любом другом месте, где нужно дать куратору выбрать
    один код из готового набора кликом.

    В отличие от Excel-комментария (openpyxl.comments.Comment) - тот
    виден только при наведении курсора и ПРОПАДАЕТ, как только ячейка
    входит в режим редактирования (жалоба Яна - при попытке ввести код
    вручную подсказка с вариантами исчезает, а запомнить/не ошибиться
    в 10 цифрах неудобно) - нативный список Excel показывает стрелку
    выбора, пока ячейка выделена, независимо от того, начал ли куратор
    печатать, и позволяет выбрать готовый код кликом, без набора вручную.
    Используется как дополнение к комментарию (который поясняет, что
    означает каждый код), а не вместо него.

    formula1 Excel - инлайн-строка "код1,код2,..." в кавычках, без
    отдельного скрытого листа-диапазона (тот же приём, что уже
    применяется в modules/dropdown_manager.py::apply_specific_dropdowns
    для материальных вариантов известных товаров). У Excel есть жёсткий
    лимит в 255 символов на такую строку - при превышении валидацию не
    строим (возвращаем None): длинный список всё равно неюзабелен, а
    сориентироваться можно по комментарию.
    """

    codes = [
        str(code).strip()
        for code in codes
        if code not in (None, "", 0) and str(code).strip()
    ]

    if not codes:
        return None

    formula = '"' + ",".join(codes) + '"'

    if len(formula) > 255:
        return None

    dv = DataValidation(
        type="list",
        formula1=formula,
        allow_blank=True,
    )
    dv.prompt = prompt
    dv.showInputMessage = True

    return dv

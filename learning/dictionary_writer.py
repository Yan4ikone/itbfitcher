"""
Точечная запись изменений в конкретную словарную константу внутри
dictionaries/all_dictionaries.py.

В отличие от dictionaries/products.py (который содержит ТОЛЬКО один
словарь PRODUCTS и поэтому whole-file pformat в learning/builder.py
безопасен) - all_dictionaries.py содержит много константа рядом:
regex-паттерны, комментарии, наборы строк. Переписать весь файл
через pformat одного модуля означало бы потерять комментарии и
рисковать поломать соседние константы.

Поэтому здесь используется ast: находим ТОЧНЫЕ границы (номера строк)
присваивания нужного имени и заменяем только эти строки, оставляя
всё остальное в файле байт-в-байт как было.
"""

import ast
from pathlib import Path
from pprint import pformat


ALL_DICTIONARIES_PATH = (
    Path(__file__).parent.parent
    / "dictionaries"
    / "all_dictionaries.py"
)


def update_dict_constant(constant_name: str, new_value: dict) -> None:

    source = ALL_DICTIONARIES_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    target = None

    for node in tree.body:

        if not isinstance(node, ast.Assign):
            continue

        if len(node.targets) != 1:
            continue

        name_node = node.targets[0]

        if isinstance(name_node, ast.Name) and name_node.id == constant_name:
            target = node
            break

    if target is None:
        raise ValueError(
            f"Константа {constant_name!r} не найдена в "
            f"{ALL_DICTIONARIES_PATH}"
        )

    lines = source.splitlines(keepends=True)

    # ast lineno/end_lineno - 1-индексированные, включительно
    start = target.lineno - 1
    end = target.end_lineno

    new_block = (
        f"{constant_name} = "
        f"{pformat(new_value, width=100, sort_dicts=False)}\n"
    )

    updated_lines = lines[:start] + [new_block] + lines[end:]

    ALL_DICTIONARIES_PATH.write_text(
        "".join(updated_lines),
        encoding="utf-8",
    )

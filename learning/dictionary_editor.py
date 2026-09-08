"""
Операции для отдельного редактора словарей (кнопка в окне обучения) -
в отличие от вкладки "Неизвестные слова" (которая копит изменения в
LearningBuilder и применяет их одной кнопкой "Применить"), редактор
работает напрямую: каждое действие куратора сразу пишется на диск.

Причина разного поведения: "Неизвестные слова" - часть batch-обзора
результатов прогона (можно передумать, снять галочку). Редактор -
самостоятельный инструмент "открыл когда угодно, поправил, закрыл",
без промежуточного состояния для отмены.
"""

import importlib

from dictionaries import all_dictionaries
from dictionaries import products as products_module
from learning.dictionary_registry import DICTIONARY_REGISTRY, get_dictionary
from learning.dictionary_writer import update_dict_constant
from utils.material_extractor import MATERIAL_GROUP_EN


MATERIAL_GROUP_RU = {en: ru for ru, en in MATERIAL_GROUP_EN.items()}


def _reload():
    importlib.invalidate_caches()
    importlib.reload(all_dictionaries)


def list_categories(dict_key: str) -> dict:
    """{группа: [слова...]} для словаря dict_key, отсортировано."""

    data = get_dictionary(dict_key)

    return {
        group: sorted(str(w) for w in words)
        for group, words in sorted(data.items())
    }


def add_word(dict_key: str, group: str, word: str) -> None:

    meta = DICTIONARY_REGISTRY.get(dict_key)

    if not meta:
        raise ValueError(f"Неизвестный словарь: {dict_key}")

    group = str(group).strip().lower()
    word = str(word).strip().lower()

    if not group or not word:
        raise ValueError("Группа и слово не должны быть пустыми")

    _reload()
    current = dict(get_dictionary(dict_key))

    existing = list(current.get(group, []))
    known = {str(w).strip().lower() for w in existing}

    if word not in known:
        existing.append(word)

    current[group] = existing

    update_dict_constant(meta["constant"], current)
    _reload()


def create_category(dict_key: str, group: str) -> None:

    meta = DICTIONARY_REGISTRY.get(dict_key)

    if not meta:
        raise ValueError(f"Неизвестный словарь: {dict_key}")

    group = str(group).strip().lower()

    if not group:
        raise ValueError("Название категории не должно быть пустым")

    _reload()
    current = dict(get_dictionary(dict_key))

    if group in current:
        raise ValueError(f"Категория «{group}» уже существует")

    current[group] = []

    update_dict_constant(meta["constant"], current)
    _reload()


def delete_word(dict_key: str, group: str, word: str) -> None:

    meta = DICTIONARY_REGISTRY.get(dict_key)

    if not meta:
        raise ValueError(f"Неизвестный словарь: {dict_key}")

    group = str(group).strip().lower()
    word = str(word).strip().lower()

    _reload()
    current = dict(get_dictionary(dict_key))

    if group not in current:
        return

    current[group] = [
        w for w in current[group]
        if str(w).strip().lower() != word
    ]

    update_dict_constant(meta["constant"], current)
    _reload()


def delete_category(dict_key: str, group: str) -> None:

    meta = DICTIONARY_REGISTRY.get(dict_key)

    if not meta:
        raise ValueError(f"Неизвестный словарь: {dict_key}")

    group = str(group).strip().lower()

    _reload()
    current = dict(get_dictionary(dict_key))

    current.pop(group, None)

    update_dict_constant(meta["constant"], current)
    _reload()


def find_group_usage(dict_key: str, group: str) -> list:
    """Список товаров (ключей products.py), у которых dropdown
    использует эту категорию как group хотя бы у одного варианта.

    Учитывает, что "материал" исторически записан в group и
    по-русски (канонический вид, как в словаре), и по-английски
    (см. MATERIAL_GROUP_EN) - обе формы считаются использованием
    одной и той же категории.
    """

    group = str(group).strip().lower()

    candidates = {group}

    if dict_key == "material":
        english = MATERIAL_GROUP_EN.get(group)
        if english:
            candidates.add(english)

        russian = MATERIAL_GROUP_RU.get(group)
        if russian:
            candidates.add(russian)

    importlib.invalidate_caches()
    importlib.reload(products_module)

    used_in = []

    for product_name, info in products_module.PRODUCTS.items():

        if not isinstance(info, dict):
            continue

        dropdown = info.get("dropdown")

        if not isinstance(dropdown, dict):
            continue

        for variant in dropdown.get("variants", []) or []:

            if not isinstance(variant, dict):
                continue

            variant_group = str(variant.get("group", "")).strip().lower()

            if variant_group in candidates:
                used_in.append(product_name)
                break

    return used_in

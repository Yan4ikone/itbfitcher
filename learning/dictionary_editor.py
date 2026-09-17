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
from pathlib import Path

from dictionaries import all_dictionaries
from dictionaries import products as products_module
from dictionaries.products_formatter import canonicalize_products, format_products
from learning.dictionary_registry import DICTIONARY_REGISTRY, get_dictionary
from learning.dictionary_writer import update_dict_constant
from utils.material_extractor import MATERIAL_GROUP_EN


MATERIAL_GROUP_RU = {en: ru for ru, en in MATERIAL_GROUP_EN.items()}

PRODUCTS_PATH = (
    Path(__file__).parent.parent
    / "dictionaries"
    / "products.py"
)


def _reload():
    importlib.invalidate_caches()
    importlib.reload(all_dictionaries)


def _reload_products():
    importlib.invalidate_caches()
    importlib.reload(products_module)


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


def add_trash_word(word: str) -> None:
    """Добавляет слово/фразу в TRASH_MARKETING - общий словарь
    маркетингового/бессмысленного мусора, который is_valid_alias()
    (learning/learning_filters.py) использует, чтобы не предлагать
    такие слова как алиасы снова и снова. Вызывается прямо из вкладки
    "Алиасы" в окне обучения - куратор видит неудачный алиас и сразу
    отправляет его в мусорный словарь, без похода в общий редактор
    словарей.

    TRASH_MARKETING - плоское множество (не структура категория->
    слова, как MATERIAL_ALIASES/GENDER_ALIASES/CHARACTERISTIC_ALIASES),
    поэтому работаем с ним напрямую, в обход dictionary_registry."""

    word = str(word or "").strip().lower()

    if not word:
        raise ValueError("Слово/фраза не должны быть пустыми")

    _reload()
    current = set(getattr(all_dictionaries, "TRASH_MARKETING", set()) or set())
    current.add(word)

    update_dict_constant("TRASH_MARKETING", current)
    _reload()


def is_trash_word(word: str) -> bool:
    """Уже есть в TRASH_MARKETING? Используется, чтобы не предлагать
    повторное добавление того, что уже туда попало."""

    word = str(word or "").strip().lower()

    if not word:
        return False

    return word in (getattr(all_dictionaries, "TRASH_MARKETING", set()) or set())


# ==================================================================
# РЕДАКТОР MATCH-СПИСКОВ И GROUP У DROPDOWN-ВАРИАНТОВ КОНКРЕТНОГО
# ТОВАРА (dictionaries/products.py, dropdown.variants[].match/.group)
#
# В отличие от словарей выше (материал/пол/характеристика,
# DICTIONARY_REGISTRY) - это НЕ общий словарь на все товары, а поле
# внутри products.py каждого конкретного товара. Раньше единственным
# способом почистить match-список или переименовать "group": "other"
# (см. products-dict-gradation-audit.md) была ручная правка
# products.py текстом - здесь curator не мог посмотреть, что там
# накопилось автообучением, и тем более убрать мусор.
#
# Пишет на диск сразу, тем же способом, что и
# learning/builder.py::save_products() - через
# dictionaries.products_formatter (сортировка, единый порядок полей,
# self-healing проверка "код не должен стоять плоско при настоящей
# градации").
# ==================================================================

def find_products(query: str, limit: int = 30) -> list:
    """Названия товаров, содержащих query (регистронезависимо) -
    для поиска в редакторе: обычный выпадающий список на 1500+
    товаров неюзабелен."""

    query = str(query or "").strip().lower()

    if not query:
        return []

    _reload_products()

    return [
        name
        for name in products_module.PRODUCTS.keys()
        if query in name.lower()
    ][:limit]


def list_product_variants(product: str) -> list:
    """[{code, group, name, match}, ...] dropdown-вариантов товара -
    свежее состояние с диска. Пустой список, если у товара нет
    dropdown или товар не найден."""

    _reload_products()

    info = products_module.PRODUCTS.get(str(product or "").strip())

    if not info:
        return []

    dropdown = info.get("dropdown") or {}

    return [dict(variant) for variant in (dropdown.get("variants") or [])]


def _write_products(current: dict) -> None:

    canonical = canonicalize_products(current)

    with open(PRODUCTS_PATH, "w", encoding="utf-8") as f:
        f.write(format_products(canonical))


def _find_variant(current: dict, product: str, code: str) -> dict:

    info = current.get(str(product or "").strip())

    if not info:
        raise ValueError(f"Товар «{product}» не найден")

    dropdown = info.get("dropdown") or {}
    variants = dropdown.get("variants") or []
    code = str(code or "").strip()

    for variant in variants:

        if str(variant.get("code", "")).strip() == code:
            return variant

    raise ValueError(f"Вариант с кодом «{code}» не найден у «{product}»")


def add_match_word(product: str, code: str, word: str) -> None:

    word = str(word or "").strip().lower()

    if not word:
        raise ValueError("Слово не должно быть пустым")

    _reload_products()
    current = products_module.PRODUCTS
    variant = _find_variant(current, product, code)

    existing = variant.setdefault("match", [])
    known = {str(w).strip().lower() for w in existing}

    if word not in known:
        existing.append(word)

    _write_products(current)
    _reload_products()


def delete_match_word(product: str, code: str, word: str) -> None:

    word = str(word or "").strip().lower()

    _reload_products()
    current = products_module.PRODUCTS
    variant = _find_variant(current, product, code)

    variant["match"] = [
        w for w in variant.get("match", [])
        if str(w).strip().lower() != word
    ]

    _write_products(current)
    _reload_products()


def set_variant_group(product: str, code: str, group: str) -> None:
    """Переименовывает group у конкретного варианта - в первую
    очередь для замены заглушки "other" (см.
    products-dict-gradation-audit.md) на осмысленную категорию."""

    group = str(group or "").strip().lower()

    if not group:
        raise ValueError("Группа не должна быть пустой")

    _reload_products()
    current = products_module.PRODUCTS
    variant = _find_variant(current, product, code)

    variant["group"] = group

    _write_products(current)
    _reload_products()

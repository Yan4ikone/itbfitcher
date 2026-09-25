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
import re
import sys
from pathlib import Path

# products.py/all_dictionaries.py переписываются на диске прямо во
# время работы (см. функции ниже: каждая читает свежее состояние
# через importlib.reload непосредственно перед записью). Стандартный
# .pyc-кэш инвалидируется по mtime, УСЕЧЁННОМУ ДО ЦЕЛОЙ СЕКУНДЫ (так
# всегда делает CPython, не особенность одной машины) - если этот
# редактор используют для двух правок подряд в пределах одной секунды,
# importlib.reload() может вернуть УСТАРЕВШЕЕ содержимое из .pyc, и
# вторая правка применится поверх старых данных, тихо потеряв первую.
# Подробности и синтетическое воспроизведение - см. MainApp.py, где
# то же самое отключается на уровне всего процесса; здесь дублируем
# на случай, если этот модуль используется без старта через MainApp.
sys.dont_write_bytecode = True

from dictionaries import all_dictionaries
from dictionaries import products as products_module
from dictionaries.products_formatter import canonicalize_products, format_products
from learning.dictionary_registry import DICTIONARY_REGISTRY, get_dictionary
from learning.dictionary_writer import update_dict_constant
from learning.learning_filters import transliterate_ru
from learning.name_normalizer import normalize_dictionary_name
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


def _name_forms(text):
    """Нормализованная форма + её транслитерация - то же представление,
    в котором learning/analyzer.py::_build_reserved_alias_map() и
    learning/archive_importer.py::_name_forms() сверяют занятость
    имени. Дублируется здесь намеренно (тот же принцип, что и
    sys.dont_write_bytecode выше) - редактор словарей самостоятельный
    инструмент, ему не следует тянуть модуль архивного импорта только
    ради одной вспомогательной функции."""

    normalized = normalize_dictionary_name(text).lower().strip()

    if not normalized:
        return ()

    return (normalized, transliterate_ru(normalized))


def check_alias_collision(product: str, alias: str) -> list:
    """Список ЧУЖИХ товаров (не product), у которых форма alias
    (прямая или транслитерация) уже занята - либо как собственное
    название, либо как уже добавленный алиас. Не запрещает ничего
    сама - куратор в редакторе решает добровольно, добавлять ли алиас
    несмотря на предупреждение (в отличие от автоматического
    archive_importer.py, здесь действие ручное и осознанное). Пустой
    список - коллизий нет.

    См. products-dict-gradation-audit.md - тот же класс проблемы, что
    "держатель"/"поло": 67 таких коллизий уже нашлись в живом словаре
    при ревизии 2026-09-24, см. list_alias_collisions() для полного
    списка."""

    product = str(product or "").strip()
    forms = set(_name_forms(alias))

    if not forms:
        return []

    _reload_products()
    owners = set()

    for name, info in products_module.PRODUCTS.items():

        if name == product:
            continue

        if not isinstance(info, dict):
            continue

        candidate_forms = set(_name_forms(name))

        for existing_alias in info.get("aliases", []) or []:
            candidate_forms.update(_name_forms(existing_alias))

        if forms & candidate_forms:
            owners.add(name)

    return sorted(owners)


def list_alias_collisions() -> list:
    """Полная диагностика живого словаря - ВСЕ случаи, где alias
    одного товара дословно (или транслитом) совпадает с названием/
    алиасом ДРУГОГО товара. Не правит ничего - только показывает,
    чтобы куратор мог пройтись и решить по каждому случаю сам (часть
    может быть намеренной, часть - нет).

    Возвращает [{"alias": str, "owners": [товары, у кого это алиас],
    "collides_with": [товары, чьё это имя/чужой алиас]}, ...],
    отсортировано по alias."""

    _reload_products()
    products = products_module.PRODUCTS

    name_owner = {}
    for name in products:
        for form in _name_forms(name):
            name_owner.setdefault(form, set()).add(name)

    alias_owner = {}
    for name, info in products.items():
        if not isinstance(info, dict):
            continue
        for alias in info.get("aliases", []) or []:
            for form in _name_forms(alias):
                alias_owner.setdefault(form, {}).setdefault(
                    str(alias).strip().lower(), set()
                ).add(name)

    results = []
    seen_keys = set()

    for form, alias_texts in alias_owner.items():

        for alias_text, owners in alias_texts.items():

            key = (form, alias_text)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            collides_with = set()

            # Совпадает с названием чужого товара.
            for other in name_owner.get(form, set()):
                if other not in owners:
                    collides_with.add(other)

            # Совпадает с алиасом чужого товара (тот же alias у 2+
            # РАЗНЫХ товаров - какой из них "правильный" при
            # классификации, неочевидно).
            if len(owners) > 1:
                collides_with.update(owners)

            if collides_with:
                results.append({
                    "alias": alias_text,
                    "owners": sorted(owners),
                    "collides_with": sorted(collides_with - owners) or sorted(owners),
                })

    results.sort(key=lambda item: item["alias"])

    return results


def list_near_duplicate_products() -> list:
    """Товары, чьи названия совпадают после strip()+lower(), но
    записаны по-разному (например, 'абажур' и 'абажур ' - лишний
    пробел) - разные ключи словаря PRODUCTS, но по факту, скорее
    всего, один и тот же товар, заведённый дважды по ошибке.

    Возвращает [{"key": нормализованная форма, "variants": [точные
    названия, ...]}, ...] - только группы из 2+ вариантов."""

    _reload_products()
    products = products_module.PRODUCTS

    groups = {}
    for name in products:
        key = name.strip().lower()
        groups.setdefault(key, []).append(name)

    return [
        {"key": key, "variants": sorted(variants)}
        for key, variants in sorted(groups.items())
        if len(variants) > 1
    ]


# ==================================================================
# GROUP (dropdown.variants[].group) - список известных значений и
# диагностика опечаток.
#
# ДОБАВЛЕНО по просьбе Яна (2026-09-25, products-dict-gradation-
# audit.md): "я не понимаю какие группы у нас есть, отсутствует выбор
# группы в программе" - до этого group редактировался обычным text
# Entry (VariantEditorWindow/"Добавить новый вариант товару" в
# learning_window.py), куратор не видел, какие значения уже приняты в
# словаре, и мог случайно опечататься (например "plastik" вместо
# "plastic") - опечатка молча ломает автоматическое определение кода
# по этому варианту (см. resolver/dropdown_axis_resolver.py/
# dropdown_resolver.py), при этом никакой ошибки нигде не появляется -
# вариант просто никогда не выбирается.
# ==================================================================

def list_known_groups() -> list:
    """Все РЕАЛЬНО используемые в products.py значения group (среди
    всех dropdown.variants всех товаров) - отсортированный список без
    повторов, для выпадающего списка в редакторе (Combobox), чтобы
    куратор видел, что уже принято, и переиспользовал существующее
    значение вместо того, чтобы печатать новое вслепую."""

    _reload_products()
    products = products_module.PRODUCTS

    groups = set()

    for info in products.values():

        if not isinstance(info, dict):
            continue

        dropdown = info.get("dropdown") or {}

        for variant in dropdown.get("variants", []) or []:

            group = str(variant.get("group", "")).strip()

            if group:
                groups.add(group)

    return sorted(groups)


# Каноническая "белая" вокабула group-значений, которые РЕАЛЬНО
# сравниваются осевыми резолверами (resolver/dropdown_axis_resolver.py)
# - только они и решают код автоматически по этой оси:
#   - MaterialAxisResolver ("material") - английские токены
#     MATERIAL_GROUP_EN.values() (metal/plastic/wood/...);
#   - GenderAxisResolver ("gender") - GENDER_ALIASES.keys();
#   - CharacteristicAxisResolver ("mechanism") - CHARACTERISTIC_ALIASES.keys();
#   - PurposeCategoryAxisResolver ("purpose_category") - PURPOSE_ALIASES.keys().
# "other" - НЕ ось, а устоявшаяся в словаре заглушка "остальное/по
# умолчанию" (166+ вариантов, см. "Обновление 2026-09-17" в аудите) -
# намеренно в списке, чтобы не считать её опечаткой.
def _known_group_vocabulary():

    return (
        set(MATERIAL_GROUP_EN.values())
        | set(all_dictionaries.GENDER_ALIASES.keys())
        | set(all_dictionaries.CHARACTERISTIC_ALIASES.keys())
        | set(all_dictionaries.PURPOSE_ALIASES.keys())
        | {"other"}
    )


def list_group_issues() -> list:
    """Диагностика ЯВНО подозрительных значений group - специально
    ОЧЕНЬ консервативная (низкий риск ложных срабатываний), а не
    полная сверка со всеми ~1600 товарами: то же group, записанное
    ПО-РУССКИ (например "картон"/"нержавеющая сталь"/"полиэстер") в
    подавляющем большинстве случаев прекрасно работает через шаг 2
    dropdown_resolver.py (буквальный поиск слова в тексте карточки) -
    и это НЕ ошибка, флагать такие как проблему значит утопить куратора
    в ~100 ложных срабатываний (см. products-dict-gradation-audit.md,
    прогон 2026-09-25) - именно этого Яна попросил избежать.

    Вместо этого здесь только два по-настоящему надёжных признака
    "эта group никогда ни с чем не совпадёт":

    1. Пустая group - вариант физически не может быть выбран ни одной
       осью (все резолверы читают variant.get("group")).
    2. Group - латиница/ASCII, но НЕ входит ни в один канонический
       английский словарь (_known_group_vocabulary() выше). Такое
       значение выглядит как попытка записать её "по конвенции"
       (английским токеном для материала/пола/механизма/назначения),
       но с опечаткой/неверным словом - типичный английский токен
       НИКОГДА не встретится буквально в русскоязычном тексте карточки
       (шаг 2 тоже не поможет), а осевые резолверы сравнивают строго
       точное совпадение, без опечаток и синонимов.

    Возвращает [{"product": ..., "code": ..., "group": ...,
    "issue": "empty"|"unrecognized"}, ...], отсортировано по товару."""

    _reload_products()
    products = products_module.PRODUCTS

    vocabulary = _known_group_vocabulary()

    issues = []

    for name, info in products.items():

        if not isinstance(info, dict):
            continue

        dropdown = info.get("dropdown") or {}

        for variant in dropdown.get("variants", []) or []:

            group = str(variant.get("group", "")).strip()
            code = str(variant.get("code", ""))
            variant_name = str(variant.get("name", ""))

            if not group:
                issues.append({
                    "product": name,
                    "code": code,
                    "variant_name": variant_name,
                    "group": group,
                    "issue": "empty",
                })
                continue

            low = group.lower()

            if (
                    low.isascii()
                    and low.replace(" ", "").isalpha()
                    and low not in vocabulary
            ):
                issues.append({
                    "product": name,
                    "code": code,
                    "variant_name": variant_name,
                    "group": group,
                    "issue": "unrecognized",
                })

    issues.sort(key=lambda item: (item["product"], item["code"]))

    return issues


def add_alias(product: str, alias: str) -> None:
    """Добавляет ОДИН алиас верхнего уровня товару - обратная операция
    к delete_alias() ниже. В отличие от автоматического обучения
    (learning/builder.py::LearningBuilder.add_alias), здесь это прямое
    осознанное действие куратора - поэтому НЕ проверяет коллизию сама
    (см. check_alias_collision() выше - GUI обязан спросить куратора
    ДО вызова этой функции, если коллизия есть, а не блокировать
    молча)."""

    alias = str(alias or "").strip().lower()

    if not alias:
        raise ValueError("Алиас не должен быть пустым")

    _reload_products()
    current = products_module.PRODUCTS
    info = current.get(str(product or "").strip())

    if not info:
        raise ValueError(f"Товар «{product}» не найден")

    product_normalized = str(product or "").strip().lower()

    if alias == product_normalized:
        raise ValueError("Алиас совпадает с названием самого товара")

    existing = list(info.get("aliases") or [])
    known = {str(a).strip().lower() for a in existing}

    if alias in known:
        raise ValueError(f"Алиас «{alias}» уже есть у «{product}»")

    existing.append(alias)
    info["aliases"] = existing

    _write_products(current)
    _reload_products()


def delete_alias(product: str, alias: str) -> None:
    """Удаляет ОДИН алиас верхнего уровня у товара (не match-слово
    dropdown-варианта - для этого delete_match_word). Нужна в первую
    очередь для ручной чистки коллизий "алиас совпадает с названием
    ДРУГОГО товара" (см. learning_filters.py::is_valid_alias,
    reserved_names) - вроде "держатель"/"derzhatel", которые могли
    попасть в aliases другого товара ДО того, как эта проверка была
    добавлена."""

    alias = str(alias or "").strip().lower()

    _reload_products()
    current = products_module.PRODUCTS
    info = current.get(str(product or "").strip())

    if not info:
        raise ValueError(f"Товар «{product}» не найден")

    info["aliases"] = [
        a for a in (info.get("aliases") or [])
        if str(a).strip().lower() != alias
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


# ==================================================================
# СТРУКТУРНЫЕ ПРАВКИ DROPDOWN-ВАРИАНТОВ (удалить/добавить/поменять
# код/перенести в другой товар)
#
# ИСТОРИЯ ПРАВКИ: до этого редактор умел только менять match/group у
# УЖЕ существующего варианта (см. добавленные выше функции). Этого
# было недостаточно, чтобы вручную вычистить мусор, накопленный
# автообучением через баг слепого слияния по коду (см.
# products-dict-gradation-audit.md, "доска" с вариантом
# карате/шлем/носилки под чужим кодом) - удалить такой вариант или
# перенести его на правильный товар можно было только вручную правкой
# products.py текстом. Здесь та же дисциплина, что и у функций выше:
# читаем с диска непосредственно перед правкой (_reload_products),
# пишем сразу через тот же canonicalize_products/format_products.
# ==================================================================

def delete_variant(product: str, code: str) -> None:
    """Удаляет вариант целиком (не только его match-слова) - для
    мусорных вариантов, которые не должны были попасть в dropdown
    товара вообще (например, накопленные через слепое слияние по
    общему коду ТН ВЭД)."""

    _reload_products()
    current = products_module.PRODUCTS
    info = current.get(str(product or "").strip())

    if not info:
        raise ValueError(f"Товар «{product}» не найден")

    dropdown = info.get("dropdown") or {}
    variants = dropdown.get("variants") or []
    code = str(code or "").strip()

    remaining = [
        v for v in variants
        if str(v.get("code", "")).strip() != code
    ]

    if len(remaining) == len(variants):
        raise ValueError(f"Вариант с кодом «{code}» не найден у «{product}»")

    dropdown["variants"] = remaining

    _write_products(current)
    _reload_products()


def add_variant(
        product: str,
        code: str,
        group: str = "",
        name: str = "",
        match: list | None = None,
) -> None:
    """Добавляет НОВЫЙ вариант (новый код) в dropdown товара - заводит
    сам блок dropdown, если у товара его ещё не было. В отличие от
    add_match_word/set_variant_group (которые правят УЖЕ существующий
    вариант), это единственный способ добавить вариант руками, минуя
    накопление через обучение - нужно, например, когда куратор сам
    знает, что товару полагается ещё один код, а не ждёт, пока это
    наберётся автоматически."""

    code = str(code or "").strip()

    if not code:
        raise ValueError("Код не должен быть пустым")

    _reload_products()
    current = products_module.PRODUCTS
    info = current.get(str(product or "").strip())

    if not info:
        raise ValueError(f"Товар «{product}» не найден")

    dropdown = info.setdefault("dropdown", {"variants": []})
    variants = dropdown.setdefault("variants", [])

    if any(str(v.get("code", "")).strip() == code for v in variants):
        raise ValueError(f"У «{product}» уже есть вариант с кодом «{code}»")

    variants.append({
        "code": code,
        "group": str(group or "").strip().lower(),
        "name": str(name or "").strip(),
        "match": [str(w).strip().lower() for w in (match or []) if str(w).strip()],
    })

    _write_products(current)
    _reload_products()


def set_variant_code(product: str, old_code: str, new_code: str) -> None:
    """Меняет код у уже существующего варианта - например, когда
    вариант изначально завели с неверным кодом."""

    new_code = str(new_code or "").strip()

    if not new_code:
        raise ValueError("Новый код не должен быть пустым")

    _reload_products()
    current = products_module.PRODUCTS
    variant = _find_variant(current, product, old_code)

    info = current.get(str(product or "").strip())
    dropdown = info.get("dropdown") or {}
    variants = dropdown.get("variants") or []

    if new_code != str(old_code or "").strip() and any(
        str(v.get("code", "")).strip() == new_code for v in variants
    ):
        raise ValueError(f"У «{product}» уже есть вариант с кодом «{new_code}»")

    variant["code"] = new_code

    _write_products(current)
    _reload_products()


def move_variant(source_product: str, code: str, target_product: str) -> None:
    """Переносит вариант ЦЕЛИКОМ (код + name + match) из одного
    товара в другой - для случаев, когда вариант когда-то приклеился
    не к тому товару (см. delete_variant docstring) и на самом деле
    описывает товар, который в словаре уже существует под другим
    именем."""

    source_product = str(source_product or "").strip()
    target_product = str(target_product or "").strip()

    if not target_product:
        raise ValueError("Не указан товар-получатель")

    if source_product == target_product:
        raise ValueError("Товар-получатель совпадает с текущим товаром")

    _reload_products()
    current = products_module.PRODUCTS

    source_info = current.get(source_product)
    if not source_info:
        raise ValueError(f"Товар «{source_product}» не найден")

    target_info = current.get(target_product)
    if not target_info:
        raise ValueError(f"Товар «{target_product}» не найден")

    variant = _find_variant(current, source_product, code)
    code = str(code or "").strip()

    target_dropdown = target_info.setdefault("dropdown", {"variants": []})
    target_variants = target_dropdown.setdefault("variants", [])

    if any(str(v.get("code", "")).strip() == code for v in target_variants):
        raise ValueError(
            f"У «{target_product}» уже есть вариант с кодом «{code}» - "
            "сначала удалите его там или измените код."
        )

    source_dropdown = source_info.get("dropdown") or {}
    source_variants = source_dropdown.get("variants") or []
    source_dropdown["variants"] = [
        v for v in source_variants
        if str(v.get("code", "")).strip() != code
    ]

    target_variants.append(dict(variant))

    _write_products(current)
    _reload_products()


# ==================================================================
# ПАТТЕРНЫ (dictionaries/products.py, info["patterns"] - регулярные
# выражения, см. resolver/candidate_scorer.py::_score_patterns,
# сверяются через re.search() с описанием карточки).
#
# До этих двух функций паттерн можно было добавить только через
# автообучение (learning/builder.py::LearningBuilder.add_pattern) -
# оно НЕ проверяет, что строка вообще является валидным regex (ошибка
# просто крешнула бы re.search() при следующей классификации). Ручной
# ввод куратора менее предсказуем, чем то, что предлагает анализатор -
# поэтому здесь, в отличие от builder.py, регекс проверяется ДО
# записи на диск (re.compile) - лучше явная ошибка в редакторе сразу,
# чем скрытый краш при следующей обработке файла.
# ==================================================================

def add_pattern(product: str, pattern: str) -> None:

    pattern = str(pattern or "").strip()

    if not pattern:
        raise ValueError("Паттерн не должен быть пустым")

    try:
        re.compile(pattern)
    except re.error as error:
        raise ValueError(f"Невалидное регулярное выражение: {error}")

    _reload_products()
    current = products_module.PRODUCTS
    info = current.get(str(product or "").strip())

    if not info:
        raise ValueError(f"Товар «{product}» не найден")

    existing = list(info.get("patterns") or [])

    if pattern in existing:
        raise ValueError(f"Паттерн «{pattern}» уже есть у «{product}»")

    existing.append(pattern)
    info["patterns"] = existing

    _write_products(current)
    _reload_products()


def delete_pattern(product: str, pattern: str) -> None:

    pattern = str(pattern or "").strip()

    _reload_products()
    current = products_module.PRODUCTS
    info = current.get(str(product or "").strip())

    if not info:
        raise ValueError(f"Товар «{product}» не найден")

    info["patterns"] = [
        p for p in (info.get("patterns") or [])
        if str(p).strip() != pattern
    ]

    _write_products(current)
    _reload_products()


# ==================================================================
# ТОВАР ЦЕЛИКОМ - создание/переименование/удаление/плоский код
#
# До этих функций такие правки делались только руками в products.py
# текстом. create_product/rename_product намеренно проверяют коллизию
# по strip()+lower() (см. list_near_duplicate_products() выше) - это
# прямая защита от повторения найденной при ревизии 2026-09-24 ошибки
# "абажур"/"абажур " (два разных ключа словаря из-за лишнего пробела,
# по факту один и тот же товар, заведённый дважды).
# ==================================================================

def _find_by_normalized_name(current: dict, name: str):
    """Ищет товар по названию, СНАЧАЛА точно, затем по strip()+lower() -
    чтобы create_product/rename_product ловили коллизию даже тогда,
    когда куратор ввёл то же название с лишним пробелом или в другом
    регистре, а не только дословное совпадение ключа."""

    name = str(name or "").strip()

    if name in current:
        return name

    normalized = name.lower()

    for existing in current:
        if existing.strip().lower() == normalized:
            return existing

    return None


def create_product(name: str, code: str = "") -> None:

    name = str(name or "").strip()

    if not name:
        raise ValueError("Название товара не должно быть пустым")

    _reload_products()
    current = products_module.PRODUCTS

    collision = _find_by_normalized_name(current, name)

    if collision is not None:
        raise ValueError(
            f"Товар «{collision}» уже существует (с точностью до "
            "пробелов/регистра) - похоже, это тот же товар."
        )

    current[name] = {
        "code": str(code or "").strip(),
        "patterns": [],
        "aliases": [],
    }

    _write_products(current)
    _reload_products()


def rename_product(old_name: str, new_name: str) -> None:

    old_name = str(old_name or "").strip()
    new_name = str(new_name or "").strip()

    if not new_name:
        raise ValueError("Новое название не должно быть пустым")

    _reload_products()
    current = products_module.PRODUCTS

    if old_name not in current:
        raise ValueError(f"Товар «{old_name}» не найден")

    if new_name != old_name:

        collision = _find_by_normalized_name(current, new_name)

        if collision is not None:
            raise ValueError(
                f"Товар «{collision}» уже существует (с точностью до "
                "пробелов/регистра)."
            )

    info = current.pop(old_name)
    current[new_name] = info

    _write_products(current)
    _reload_products()


def delete_product(name: str) -> None:
    """Удаляет товар целиком - вместе с его кодом, паттернами,
    алиасами и dropdown-вариантами. Необратимо (как и всё в этом
    редакторе - см. модульный docstring)."""

    name = str(name or "").strip()

    _reload_products()
    current = products_module.PRODUCTS

    if name not in current:
        raise ValueError(f"Товар «{name}» не найден")

    current.pop(name)

    _write_products(current)
    _reload_products()


def set_product_code(product: str, code: str) -> None:
    """Меняет плоский info["code"]. Для товара с настоящей градацией
    по dropdown (2+ разных кода среди вариантов) canonicalize_products()
    при следующем сохранении всё равно обнулит плоский код обратно
    (см. dictionaries/products_formatter.py::canon_entry) - это
    самовосстанавливающийся guard от бага, разобранного в
    products-dict-gradation-audit.md, а не ошибка редактора."""

    _reload_products()
    current = products_module.PRODUCTS
    info = current.get(str(product or "").strip())

    if not info:
        raise ValueError(f"Товар «{product}» не найден")

    info["code"] = str(code or "").strip()

    _write_products(current)
    _reload_products()

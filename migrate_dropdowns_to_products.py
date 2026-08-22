from __future__ import annotations

import ast
import importlib
import shutil
import sys
from datetime import datetime
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PRODUCTS_FILE = (
    BASE_DIR
    / "dictionaries"
    / "products.py"
)

DROPDOWN_FILE = (
    BASE_DIR
    / "dictionaries"
    / "dropdown_lists.py"
)

BACKUP_DIR = (
    BASE_DIR
    / "dictionaries"
    / "backup"
)


# ============================================================
# SETTINGS
# ============================================================

# Если True:
#   программа только проверит, что будет сделано,
#   но НЕ изменит products.py.
DRY_RUN = False


# Если True:
#   существующее поле "dropdown" у товара будет заменено.
#
# По умолчанию False:
#   если dropdown уже есть, мы его НЕ трогаем.
OVERWRITE_EXISTING_DROPDOWN = False


# Если True:
#   после миграции проверяем products.py через AST
#   и импортируем его в отдельном модуле.
VERIFY_AFTER_WRITE = True


# ============================================================
# OUTPUT
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# LOAD PRODUCTS.PY
# ============================================================

def load_products():
    """
    Загружает PRODUCTS из текущего products.py.
    """

    if not PRODUCTS_FILE.exists():
        raise FileNotFoundError(
            f"Не найден файл:\n{PRODUCTS_FILE}"
        )

    import dictionaries.products as products_module

    importlib.invalidate_caches()
    products_module = importlib.reload(products_module)

    products = getattr(
        products_module,
        "PRODUCTS",
        None,
    )

    if not isinstance(products, dict):
        raise RuntimeError(
            "PRODUCTS в products.py не является dict."
        )

    return products


# ============================================================
# LOAD DROPDOWNS
# ============================================================

def load_dropdowns():
    """
    Загружает DROPDOWN_LISTS.
    """

    if not DROPDOWN_FILE.exists():
        raise FileNotFoundError(
            f"Не найден файл:\n{DROPDOWN_FILE}"
        )

    import dictionaries.dropdown_lists as dropdown_module

    importlib.invalidate_caches()
    dropdown_module = importlib.reload(
        dropdown_module
    )

    dropdowns = getattr(
        dropdown_module,
        "DROPDOWN_LISTS",
        None,
    )

    if not isinstance(dropdowns, dict):
        raise RuntimeError(
            "DROPDOWN_LISTS в dropdown_lists.py "
            "не является dict."
        )

    return dropdowns


# ============================================================
# NORMALIZE VARIANT
# ============================================================

def normalize_variant(variant):
    """
    Нормализуем одну запись dropdown.

    Сохраняем только необходимые поля:
        code
        name
        group

    Никаких изменений существующей логики.
    """

    if not isinstance(variant, dict):
        raise RuntimeError(
            f"Некорректный variant: {variant!r}"
        )

    code = str(
        variant.get("code", "")
    ).strip()

    name = str(
        variant.get("name", "")
    ).strip()

    group = str(
        variant.get("group", "")
    ).strip()

    if not code:
        raise RuntimeError(
            f"У dropdown-варианта отсутствует code: "
            f"{variant!r}"
        )

    return {
        "code": code,
        "name": name,
        "group": group,
    }


# ============================================================
# NORMALIZE DROPDOWN
# ============================================================

def normalize_dropdown(product, data):
    """
    Преобразует:

        {
            "title": "...",
            "variants": [...]
        }

    в структуру, которую будем хранить внутри PRODUCTS.
    """

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Dropdown для {product!r} "
            f"не является dict."
        )

    raw_variants = data.get(
        "variants",
        [],
    )

    if not isinstance(raw_variants, list):
        raise RuntimeError(
            f"variants для {product!r} "
            f"не является list."
        )

    variants = []

    for variant in raw_variants:
        variants.append(
            normalize_variant(variant)
        )

    return {
        "title": str(
            data.get(
                "title",
                "Выберите вариант",
            )
        ),
        "variants": variants,
    }


# ============================================================
# VALIDATE DROPDOWNS
# ============================================================

def validate_dropdowns(dropdowns):
    """
    Полная предварительная проверка DROPDOWN_LISTS.

    ВАЖНО:
    пока хотя бы один элемент неправильный,
    products.py НЕ изменяется.
    """

    normalized = {}

    for product, data in dropdowns.items():

        if not isinstance(product, str):
            raise RuntimeError(
                f"Ключ dropdown не является str: "
                f"{product!r}"
            )

        product = product.strip()

        if not product:
            raise RuntimeError(
                "Обнаружен пустой ключ dropdown."
            )

        normalized[product] = normalize_dropdown(
            product,
            data,
        )

    return normalized


# ============================================================
# BACKUP
# ============================================================

def create_backup():
    """
    Создаёт резервную копию products.py
    ДО любых изменений.
    """

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_file = (
        BACKUP_DIR
        / f"products_before_dropdown_{timestamp}.py"
    )

    shutil.copy2(
        PRODUCTS_FILE,
        backup_file,
    )

    return backup_file


# ============================================================
# SERIALIZE PRODUCTS
# ============================================================

def write_products(products):
    """
    Записывает PRODUCTS полностью.

    Используем pprint-подобный формат через repr,
    сохраняя валидный Python-код.
    """

    from pprint import pformat

    content = (
        "# -*- coding: utf-8 -*-\n"
        "\n"
        "# AUTO-GENERATED/UPDATED BY "
        "migrate_dropdowns_to_products.py\n"
        "# DO NOT DELETE PRODUCTS MANUALLY.\n"
        "\n"
        "PRODUCTS = "
        + pformat(
            products,
            width=140,
            sort_dicts=False,
        )
        + "\n"
    )

    temp_file = PRODUCTS_FILE.with_suffix(
        ".py.tmp"
    )

    try:

        temp_file.write_text(
            content,
            encoding="utf-8",
        )

        # Проверяем синтаксис ДО замены оригинального файла.
        source = temp_file.read_text(
            encoding="utf-8"
        )

        ast.parse(
            source,
            filename=str(temp_file),
        )

        temp_file.replace(
            PRODUCTS_FILE
        )

    finally:

        if temp_file.exists():
            temp_file.unlink(
                missing_ok=True
            )


# ============================================================
# VERIFY PYTHON FILE
# ============================================================

def verify_products_file(
    expected_products_count,
    expected_dropdowns,
):
    """
    Проверяет уже записанный products.py.

    Проверяем:
        1. файл существует;
        2. Python-синтаксис;
        3. PRODUCTS является dict;
        4. количество товаров не уменьшилось;
        5. каждый dropdown существует;
        6. количество variants совпадает;
        7. code/name/group совпадают.
    """

    source = PRODUCTS_FILE.read_text(
        encoding="utf-8"
    )

    ast.parse(
        source,
        filename=str(PRODUCTS_FILE),
    )

    # Загружаем через отдельный namespace,
    # чтобы не зависеть от старого import cache.
    namespace = {}

    exec(
        compile(
            source,
            str(PRODUCTS_FILE),
            "exec",
        ),
        namespace,
    )

    products = namespace.get(
        "PRODUCTS"
    )

    if not isinstance(products, dict):
        raise RuntimeError(
            "После записи PRODUCTS не является dict."
        )

    if len(products) != expected_products_count:
        raise RuntimeError(
            "После миграции изменилось количество "
            f"PRODUCTS: было/ожидалось "
            f"{expected_products_count}, "
            f"получено {len(products)}"
        )

    for product, expected_dropdown in (
        expected_dropdowns.items()
    ):

        if product not in products:
            raise RuntimeError(
                f"После миграции потерян товар: "
                f"{product!r}"
            )

        info = products[product]

        if not isinstance(info, dict):
            raise RuntimeError(
                f"PRODUCTS[{product!r}] "
                "не является dict."
            )

        actual_dropdown = info.get(
            "dropdown"
        )

        if actual_dropdown != expected_dropdown:
            raise RuntimeError(
                "Dropdown не совпадает после записи "
                f"для товара {product!r}."
            )

    return products


# ============================================================
# MAIN MIGRATION
# ============================================================

def migrate():
    log("")
    log("=" * 90)
    log("MIGRATION: DROPDOWN_LISTS -> PRODUCTS")
    log("=" * 90)
    log("")

    log(
        f"PRODUCTS : {PRODUCTS_FILE}"
    )

    log(
        f"DROPDOWNS: {DROPDOWN_FILE}"
    )

    log("")

    # --------------------------------------------------------
    # 1. LOAD
    # --------------------------------------------------------

    products = load_products()
    dropdowns = load_dropdowns()

    original_products_count = len(
        products
    )

    log(
        f"PRODUCTS товаров : "
        f"{original_products_count}"
    )

    log(
        f"DROPDOWN товаров: "
        f"{len(dropdowns)}"
    )

    log("")

    # --------------------------------------------------------
    # 2. FULL VALIDATION BEFORE CHANGES
    # --------------------------------------------------------

    log(
        "[1/6] Проверяем весь DROPDOWN_LISTS..."
    )

    normalized_dropdowns = validate_dropdowns(
        dropdowns
    )

    log(
        f"      ✓ Проверено dropdown: "
        f"{len(normalized_dropdowns)}"
    )

    # --------------------------------------------------------
    # 3. PREPARE MERGE
    # --------------------------------------------------------

    log(
        "[2/6] Готовим объединение..."
    )

    added = 0
    updated = 0
    skipped = 0

    # Делаем глубокую копию через обычные структуры,
    # чтобы исходный импортированный PRODUCTS
    # не мутировался до момента записи.
    import copy

    new_products = copy.deepcopy(
        products
    )

    expected_dropdowns = {}

    for product, dropdown in (
        normalized_dropdowns.items()
    ):

        if product not in new_products:

            # ------------------------------------------------
            # Новый продукт.
            #
            # Мы НЕ создаём ему code автоматически.
            # Dropdown хранится отдельно.
            # ------------------------------------------------

            new_products[product] = {
                "code": "",
                "dropdown": dropdown,
            }

            added += 1

        else:

            info = new_products[product]

            if not isinstance(info, dict):
                raise RuntimeError(
                    f"PRODUCTS[{product!r}] "
                    "не является dict."
                )

            existing_dropdown = info.get(
                "dropdown"
            )

            if existing_dropdown is not None:

                if (
                    not OVERWRITE_EXISTING_DROPDOWN
                ):
                    skipped += 1

                    expected_dropdowns[
                        product
                    ] = existing_dropdown

                    continue

            info["dropdown"] = dropdown
            updated += 1

        expected_dropdowns[
            product
        ] = dropdown

    log(
        f"      Новых товаров : {added}"
    )

    log(
        f"      Обновлено      : {updated}"
    )

    log(
        f"      Пропущено      : {skipped}"
    )

    log("")

    # --------------------------------------------------------
    # 4. DRY RUN
    # --------------------------------------------------------

    if DRY_RUN:

        log(
            "[DRY RUN] products.py НЕ изменён."
        )

        log("")
        log(
            "Примеры переноса:"
        )

        for index, (
            product,
            dropdown,
        ) in enumerate(
            normalized_dropdowns.items()
        ):

            if index >= 10:
                break

            log(
                f"  {product}: "
                f"{len(dropdown['variants'])} variants"
            )

        log("")
        return

    # --------------------------------------------------------
    # 5. BACKUP + WRITE
    # --------------------------------------------------------

    log(
        "[3/6] Создаём backup..."
    )

    backup_file = create_backup()

    log(
        f"      ✓ Backup: {backup_file}"
    )

    log("")

    try:

        log(
            "[4/6] Записываем products.py..."
        )

        write_products(
            new_products
        )

        log(
            "      ✓ products.py записан"
        )

        # ----------------------------------------------------
        # 6. VERIFY
        # ----------------------------------------------------

        if VERIFY_AFTER_WRITE:

            log(
                "[5/6] Проверяем результат..."
            )

            verify_products_file(
                original_products_count
                + added,
                expected_dropdowns,
            )

            log(
                "      ✓ Проверка пройдена"
            )

    except Exception:

        log("")
        log(
            "!!! ОШИБКА МИГРАЦИИ !!!"
        )

        log(
            "Восстанавливаем backup..."
        )

        shutil.copy2(
            backup_file,
            PRODUCTS_FILE,
        )

        log(
            "✓ products.py восстановлен."
        )

        raise

    # --------------------------------------------------------
    # DONE
    # --------------------------------------------------------

    log("")
    log(
        "[6/6] МИГРАЦИЯ ЗАВЕРШЕНА"
    )

    log("")
    log(
        f"Товаров было : {original_products_count}"
    )

    log(
        f"Добавлено    : {added}"
    )

    log(
        f"Обновлено    : {updated}"
    )

    log(
        f"Пропущено    : {skipped}"
    )

    log(
        f"Теперь       : {len(new_products)}"
    )

    log("")
    log(
        f"Backup: {backup_file}"
    )

    log("")
    log("=" * 90)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:
        migrate()

    except Exception as exc:

        log("")
        log(
            "МИГРАЦИЯ ОСТАНОВЛЕНА:"
        )
        log(
            repr(exc)
        )

        sys.exit(1)
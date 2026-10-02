"""
Единая канонизация и форматирование dictionaries/products.py.
canonicalize_products() применяется ПРЯМО ПЕРЕД записью на диск -
и как чистка схемы, и как самовосстанавливающийся guard от этого
класса бага.
"""

FIELD_ORDER = [
    "code", "patterns", "aliases", "synonyms", "excludes_context",
    "requires_context", "material_codes", "dropdown",
]
VARIANT_FIELD_ORDER = ["code", "name", "group", "match", "min_volume_l", "max_volume_l"]
DROPDOWN_FIELD_ORDER = ["title", "axis", "variants"]


def _dedup_preserve_order(items):
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _canon_variant(variant):
    out = {}
    for key in VARIANT_FIELD_ORDER:
        if key in variant:
            out[key] = variant[key]
    for key in variant:
        if key not in out:
            out[key] = variant[key]
    return out


def _canon_dropdown(dropdown):
    out = {}
    for key in DROPDOWN_FIELD_ORDER:
        if key in dropdown:
            if key == "variants":
                out[key] = [_canon_variant(v) for v in dropdown[key]]
            else:
                out[key] = dropdown[key]
    for key in dropdown:
        if key not in out:
            out[key] = dropdown[key]
    return out


def _has_real_gradation(dropdown):
    """2+ РАЗНЫХ кода среди вариантов - настоящая градация, а не
    декоративный dropdown (когда все варианты дают тот же код, что
    и так стоял бы в плоском "code")."""

    if not dropdown:
        return False

    variants = dropdown.get("variants") or []
    codes = {str(v.get("code", "")).strip() for v in variants}
    codes.discard("")

    return len(codes) >= 2


def canon_entry(name, info):
    """Канонизирует одну запись товара:
    - убирает пустой material_codes: {} (функционально не отличается
      от отсутствующего ключа - info.get("material_codes", {}));
    - если есть настоящая градация по dropdown И код НЕ защищён
      через material_codes конкретного товара (material_codes - это
      отдельная, более точная ветка резолвера, которая не запускает
      общий фоновый поиск материала - см. resolver/material_resolver.py)
      - плоский "code" обнуляется, иначе DecisionEngine может решить,
      что материал/признак уже определён, и пропустить выбор варианта
      целиком (см. модуль docstring выше);
    - дедуплицирует aliases/patterns и убирает название товара из
      его же aliases.
    """

    out = {}

    dropdown = info.get("dropdown")
    material_codes = info.get("material_codes") or {}
    code = info.get("code", "")

    # 2026-10-01: плоский код, совпадающий с кодом одного из вариантов,
    # - это вариант по умолчанию (товар-категория, бывшие material_codes),
    # его оставляем. Выбор варианта он больше не блокирует - см.
    # engines/decision_engine.py (material_already_resolved).
    variant_codes = {
        str(v.get("code", "")).strip()
        for v in (dropdown or {}).get("variants") or []
    }

    if (
        dropdown and _has_real_gradation(dropdown) and not material_codes
        and str(code or "").strip() not in variant_codes
    ):
        code = ""

    for key in FIELD_ORDER:

        if key == "code":
            out[key] = code
            continue

        if key == "material_codes":
            if material_codes:
                out[key] = material_codes
            continue

        if key == "dropdown":
            if dropdown:
                out[key] = _canon_dropdown(dropdown)
            continue

        if key == "aliases":
            aliases = _dedup_preserve_order(info.get("aliases", []))
            out[key] = [a for a in aliases if a != name]
            continue

        if key == "patterns":
            out[key] = _dedup_preserve_order(info.get("patterns", []))
            continue

        if key in ("synonyms", "excludes_context", "requires_context"):
            values = _dedup_preserve_order(info.get(key) or [])
            if key == "synonyms":
                values = [v for v in values if v != name]
            if values:
                out[key] = values
            continue

        if key in info:
            out[key] = info[key]

    # Остальные поля (score_words, display_name и т.п.) раньше молча
    # терялись при каждой записи словаря - в том числе excludes_context
    # / requires_context. Теперь сохраняются как есть, после основных.
    for key, value in info.items():
        if key not in out and key not in FIELD_ORDER:
            out[key] = value

    return out


def _sort_key(name):
    # Кириллица: "ё" сортируем как "е"
    return name.replace("ё", "е").replace("Ё", "Е")


def canonicalize_products(data: dict) -> dict:
    """Возвращает НОВЫЙ dict: те же товары, отсортированные по
    названию, каждая запись канонизирована через canon_entry()."""

    return {
        name: canon_entry(name, data[name])
        for name in sorted(data.keys(), key=_sort_key)
    }


def _fmt(value, indent):

    pad = "    " * indent
    pad_in = "    " * (indent + 1)

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        for k, v in value.items():
            lines.append(f"{pad_in}{k!r}: {_fmt(v, indent + 1)},")
        lines.append(f"{pad}}}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            return "[]"
        lines = ["["]
        for item in value:
            lines.append(f"{pad_in}{_fmt(item, indent + 1)},")
        lines.append(f"{pad}]")
        return "\n".join(lines)

    if isinstance(value, str):
        return repr(value)

    if value is None:
        return "None"

    if isinstance(value, bool):
        return "True" if value else "False"

    if isinstance(value, (int, float)):
        return repr(value)

    raise TypeError(f"Unsupported type in products.py value: {type(value)}")


def format_products(data: dict) -> str:
    """Сериализует PRODUCTS в исходный код products.py - по одному
    товару и по одному элементу списка на строку, единый порядок
    полей. Не сортирует сама - ожидает уже отсортированный dict
    (см. canonicalize_products)."""

    lines = ["PRODUCTS = {"]

    for key, value in data.items():
        lines.append(f"    {key!r}: {_fmt(value, 1)},")

    lines.append("}")
    lines.append("")

    return "\n".join(lines)

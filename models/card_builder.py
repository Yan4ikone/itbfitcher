from urllib.parse import urlparse, unquote
import re

from modules.product_card import ProductCard
from utils.quantity_extractor import (
    extract_quantity,
    is_heterogeneous_kit,
    strip_heterogeneous_kit_segments,
)
from utils.material_extractor import extract_material


FIELDS = [
    "Тип",
    "Тип товара",
    "Назначение",
    "Особенности",
    "Комплектация",
    "Материал",
    "Форма",
    "Конструкция"
]

def extract_slug(url):

    path = unquote(urlparse(url).path)
    m = re.search(r"/product/(.+?)-\d+/?$", path)

    if not m:
        return ""

    slug = m.group(1)
    slug = slug.replace("-", " ")
    slug = re.sub(r"\s+", " ", slug)

    return slug.strip().lower()

def build_from_excel(description, characteristics="", normalized=""):
    card = ProductCard()
    card.title = description
    card.description = description
    card.cleaned_text = normalized or description

    if characteristics:
        card.specs["Характеристики"] = characteristics

    text = " ".join(filter(None, [description, characteristics]))

    quantity = extract_quantity(text)

    if quantity:
        card.quantity = quantity
    material = extract_material(text)

    if material:
        card.material = material
        card.specs.setdefault("Материал", material)

    return card

def build_product_card(url, parsed, raw_text):

    card = ProductCard()
    card.url = url
    card.slug = extract_slug(url)
    card.url_product_name = card.slug
    card.raw_text = raw_text
    card.title = parsed.get("title", "")
    card.description = parsed.get("description", "")
    card.specs = parsed.get("specs", {})
    card.breadcrumbs = parsed.get("breadcrumbs", [])
    card.images = parsed.get("images", [])

    if not card.title:
        card.title = card.slug

    if not card.cleaned_text:
        if not card.cleaned_text:
            card.cleaned_text = (
                    card.title
                    or card.slug
                    or card.description
            )

    if not card.description or card.description == "Распродажа":
        card.description = card.slug

    for key, value in card.specs.items():

        key_l = str(key or "").strip().lower()
        value_str = str(value or "").strip()

        if not value_str:
            continue
        # ======================================================
        # MATERIAL
        # ======================================================
        if (
                "материал" in key_l
                or "состав" in key_l
        ):
            if not card.material:
                card.material = value_str
        # ======================================================
        # QUANTITY
        # ======================================================
        if (
                "количество" in key_l
                or "кол-во" in key_l
                or "кол во" in key_l
                or "в упаковке" in key_l
                or "комплект" in key_l
                or "набор" in key_l
        ):
            # "Комплектация"/"Состав набора" - это ПЕРЕЧЕНЬ того, что
            # лежит в наборе (пылесос, насадка-щётка, шланг), а не
            # количество экземпляров товара. Раньше "комплект" in key_l
            # ловил и "Комплектация" тоже, и если в её значении
            # встречалось "2 шт"/"2 предмета" (сумма РАЗНЫХ компонентов),
            # это ошибочно становилось количеством товара - "пылесос
            # 2 шт" вместо "пылесос (в комплекте с щёткой)".
            is_composition_key = (
                "комплектация" in key_l
                or "состав набора" in key_l
                or "состав комплекта" in key_l
            )

            if is_composition_key and is_heterogeneous_kit(value_str):
                quantity = ""
            else:
                quantity = extract_quantity(value_str)

            # Частый случай на Ozon: единица уже в НАЗВАНИИ поля
            # ("Количество в упаковке, шт"), а само значение -
            # просто голое число ("5"). Тогда unit берём из key.
            if not quantity and value_str.isdigit() and not is_composition_key:

                number = int(value_str)

                if number >= 2:

                    if "компл" in key_l:
                        unit = "комплект"
                    elif "набор" in key_l:
                        unit = "набор"
                    elif "пар" in key_l:
                        unit = "пар"
                    else:
                        unit = "шт"

                    quantity = f"{number} {unit}"

            if quantity:
                card.quantity = quantity
        # ======================================================
        # VOLUME
        # ======================================================
        if (
                "объем" in key_l
                or "объём" in key_l
        ):
            volume = _extract_volume(value_str)

            if volume:
                card.volume = volume
        # ======================================================
        # COUNTRY
        # ======================================================
        if "страна" in key_l:
            if not card.country:
                card.country = value_str
        # ======================================================
        # BRAND
        # ======================================================
        if "бренд" in key_l:
            if not card.brand:
                card.brand = value_str
        # ------------------------------------------------------------
        # FALLBACK: если ни один спек не дал количество (его вообще
        # нет как отдельного поля, оно только в заголовке - как
        # "Носки для девочек, 5 пар") - пробуем достать из текста.
        # ------------------------------------------------------------
        if not card.quantity:

            fallback_text = strip_heterogeneous_kit_segments(
                " ".join(filter(None, [card.title, card.description]))
            )
            quantity = extract_quantity(fallback_text)

            if quantity:
                card.quantity = quantity

    # ------------------------------------------------------------
    # МАТЕРИАЛ FALLBACK
    #
    # Если ни один spec-ключ не содержал "материал"/"состав" (Ozon
    # иногда отдаёт материал только текстом внутри описания, а не
    # отдельным полем характеристик), пробуем вытащить его оттуда же,
    # где это уже делает parser/ozon_parser.py - тем же общим
    # extract_material(), чтобы не поддерживать вторую копию regex.
    # ------------------------------------------------------------
    if not card.material:

        material = extract_material(
            " ".join(filter(None, [card.description, card.raw_text]))
        )

        if material:
            card.material = material

    card.sections = parsed.get("sections", {})
    card.parser_log = parsed.get("parser_log", [])

    return card

def _extract_volume(value):

    value = str(value or "").strip().lower()

    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)

    match = re.fullmatch(
        r"(\d+(?:[.,]\d+)?)\s*(мл)",
        value,
    )
    if match:
        return f"{match.group(1)} {match.group(2)}"

    return ""
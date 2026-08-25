from urllib.parse import urlparse, unquote
import re

from modules.product_card import ProductCard
from utils.quantity_extractor import extract_quantity


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
            quantity = extract_quantity(value_str)
            # Частый случай на Ozon: единица уже в НАЗВАНИИ поля
            # ("Количество в упаковке, шт"), а само значение -
            # просто голое число ("5"). Тогда unit берём из key.
            if not quantity and value_str.isdigit():

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

            quantity = extract_quantity(
                " ".join(filter(None, [card.title, card.description]))
            )

            if quantity:
                card.quantity = quantity
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
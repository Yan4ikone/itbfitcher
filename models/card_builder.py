from urllib.parse import urlparse, unquote
import re

from modules.product_card import ProductCard


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

        key_l = key.lower()

        if any(
                x in key_l
                for x in (
                        "количество",
                        "в упаковке",
                        "количество товара",
                        "комплект",
                        "шт",
                )
        ):
            card.quantity = str(value)

        if key_l.strip() == "материал":
            card.material = str(value)

        if "страна" in key_l:
            card.country = str(value)

        if "бренд" in key_l:
            card.brand = str(value)

    card.sections = parsed.get("sections", {})
    card.parser_log = parsed.get("parser_log", [])

    return card
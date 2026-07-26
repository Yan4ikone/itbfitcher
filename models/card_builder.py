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

    return slug.strip()

def build_from_excel(description, characteristics=""):
    card = ProductCard()
    card.title = description
    card.description = description
    card.cleaned_text = description

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
    for key, value in card.specs.items():
        key_l = key.lower()
        if "количество" in key_l:
            card.quantity = str(value)
            break

    for key, value in card.specs.items():
        key_l = key.lower()
        if "материал" in key_l:
            card.material = str(value)
            break
    card.sections = parsed.get("sections", {})
    card.parser_log = parsed.get("parser_log", [])

    return card
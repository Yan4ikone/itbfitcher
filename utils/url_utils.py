import re


def normalize_ozon_url(url: str) -> str:
    if not url:
        return ""

    match = re.search(r"/product/(?:[^/]+-)?(\d+)", url)

    if not match:
        return url

    product_id = match.group(1)

    return f"https://www.ozon.ru/product/{product_id}/"
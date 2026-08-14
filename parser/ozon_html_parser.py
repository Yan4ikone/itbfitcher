"""
Парсер карточки товара Ozon из сохранённого / полученного HTML.

Два независимых источника данных:
1. <script type="application/ld+json"> - структурированная разметка
   Product (schema.org), которую Ozon отдаёт для поисковиков.
   Даёт: название, описание, цену, картинку, sku, рейтинг.
2. Блоки <dl><dt>Название</dt><dd>Значение</dd></dl> в секции
   характеристик - обычная семантическая HTML-структура.

ПРИНЦИПИАЛЬНО: НЕ используем классы вида "pdp_i8a", "pdp_a9i" и т.п.
Это хэши CSS-модулей (CSS-in-JS), они перегенерируются при каждом
деплое фронтенда Ozon и никак не связаны со смыслом контента.
Селекторы строятся только по структуре тегов (dl > dt > dd) и по
семантическим атрибутам (type="application/ld+json"), которые
Ozon не может менять без поломки собственной SEO-разметки.
"""

import json
from bs4 import BeautifulSoup


def parse_ozon_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    result = {
        "title": "",
        "description": "",
        "price": None,
        "currency": None,
        "sku": "",
        "brand": "",
        "main_image": "",
        "specs": {},
        "specs_count": 0,
    }
    _parse_ld_json(soup, result)
    _parse_specs(soup, result)

    return result


def _parse_ld_json(soup: BeautifulSoup, result: dict) -> None:
    """Источник 1: структурированные данные Product."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        # ld+json на странице может быть массивом объектов разных типов
        candidates = data if isinstance(data, list) else [data]

        for item in candidates:
            if not isinstance(item, dict):
                continue
            if item.get("@type") != "Product":
                continue

            result["title"] = item.get("name", "").strip()
            result["description"] = item.get("description", "").strip()
            result["sku"] = str(item.get("sku", "")).strip()
            result["brand"] = (item.get("brand") or "").strip()

            image = item.get("image")
            if isinstance(image, list) and image:
                result["main_image"] = image[0]
            elif isinstance(image, str):
                result["main_image"] = image

            offers = item.get("offers") or {}
            if isinstance(offers, dict):
                price = offers.get("price")
                if price is not None:
                    try:
                        result["price"] = float(price)
                    except (TypeError, ValueError):
                        result["price"] = None
                result["currency"] = offers.get("priceCurrency")

            return  # первого Product-блока достаточно


def _parse_specs(soup: BeautifulSoup, result: dict) -> None:
    """
    Источник 2: характеристики товара.

    Структура: <dl><dt><span>Название</span></dt><dd>Значение</dd></dl>
    Внутри dt может быть несколько вложенных span - берём весь
    текст dt целиком. Внутри dd иногда лежит иконка "скопировать"
    (для Артикула) - она не текстовая, get_text() её не подхватит.
    """
    specs = {}

    for dl in soup.find_all("dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if not dt or not dd:
            continue

        key = dt.get_text(strip=True)
        value = dd.get_text(strip=True)

        if key and value:
            specs[key] = value

    result["specs"] = specs
    result["specs_count"] = len(specs)


def parse_ozon_page(page) -> dict:
    """
    Интеграция с Playwright: берём HTML уже отрисованной страницы
    (page.content() отдаёт текущий DOM, включая всё, что дорисовал JS)
    и парсим его этим же кодом. Никакого ожидания network idle не
    нужно - только дождаться, что нужный блок появился в DOM.
    """
    page.wait_for_selector("dl dt, script[type='application/ld+json']", timeout=15000)
    html = page.content()
    return parse_ozon_html(html)


if __name__ == "__main__":
    import sys

    path = sys.argv[1]
    with open(path, encoding="utf-8", errors="ignore") as f:
        html = f.read()

    data = parse_ozon_html(html)

    print("TITLE:", data["title"])
    print("DESCRIPTION:", len(data["description"]), "chars")
    print("  ->", data["description"][:150].replace("\n", " "), "...")
    print("PRICE:", data["price"], data["currency"])
    print("SKU:", data["sku"])
    print("MAIN IMAGE:", data["main_image"])
    print()
    print(f"SPECS ({data['specs_count']}):")
    for k, v in data["specs"].items():
        print(f"  {k}: {v}")
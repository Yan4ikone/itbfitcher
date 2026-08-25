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
import asyncio
import re
import logging
from bs4 import BeautifulSoup


log = logging.getLogger(__name__)

def parse_ozon_html(html: str) -> dict:
    # lxml - C-расширение, заметно (обычно в разы) быстрее html.parser
    # на больших документах вроде страниц Ozon. Фоллбэк на html.parser,
    # если lxml не установлен в окружении - тогда всё равно работает,
    # просто медленнее.
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
    result = {
        "title": "",
        "description": "",
        "price": None,
        "currency": None,
        "sku": "",
        "brand": "",
        "main_image": "",
        "images": [],
        "specs": {},
        "specs_count": 0,
        "material": "",
        "breadcrumbs": [],}
    _parse_ld_json(soup, result)
    _parse_specs(soup, result)
    _parse_breadcrumbs(soup, result)
    _parse_images(soup, result)
    _extract_material(result)

    # ------------------------------------------------------
    # FALLBACK: <title> СТРАНИЦЫ
    #
    # Бывает, что Ozon вместо карточки товара отдаёт другую
    # страницу (например, редирект на /search/, если конкретный
    # SKU недоступен) - там нет ни ld+json Product, ни характеристик,
    # но тег <title> почти всегда содержит осмысленное название
    # ("Платье - купить на OZON"). Используем как резерв, когда
    # ld+json ничего не дал.
    # ------------------------------------------------------
    if not result["title"]:
        result["title"] = _extract_title_tag(soup)

    if not result["description"] and result["title"]:
        result["description"] = result["title"]

    return result


def _extract_title_tag(soup: BeautifulSoup) -> str:
    tag = soup.find("title")

    if not tag:
        return ""

    text = tag.get_text(strip=True)

    if not text:
        return ""

    # Ozon обычно приписывает маркетинговый хвост вида
    # "Платье - купить на OZON по низкой цене (123456)" -
    # обрезаем всё после " - купить", оставляя только название.
    text = re.split(r"\s*[-–—]\s*купить\b", text, maxsplit=1, flags=re.IGNORECASE)[0]

    return text.strip()


def extract_search_query_hint(url: str) -> str:
    """
    Ещё один резервный источник названия - специфично для страниц
    поиска Ozon (.../search/?...&text=<название>&product_id=...).
    Ozon сам кладёт туда текст запроса, обычно это и есть название
    товара. Используется, когда даже <title> страницы не дал ничего
    полезного.
    """
    from urllib.parse import urlparse, parse_qs, unquote

    try:
        parsed = urlparse(url)

        if "/search" not in parsed.path:
            return ""

        params = parse_qs(parsed.query)
        text_values = params.get("text")

        if not text_values:
            return ""

        return unquote(text_values[0]).strip()
    except Exception:
        return ""


# Порядок важен: сначала точное совпадение "Материал", затем более
# специфичные варианты. Если у товара несколько материал-полей
# (верх/подошва/подкладка), для ТН ВЭД обычно важнее основной/верхний.
_MATERIAL_KEY_PRIORITY = (
    "материал",
    "материал верха",
    "материал изделия",
    "состав",
)

def _extract_material(result: dict) -> None:
    specs = result.get("specs", {})
    if not specs:
        return

    # 1. Точное совпадение по приоритету
    lowered = {k.lower().strip(): v for k, v in specs.items()}
    for candidate in _MATERIAL_KEY_PRIORITY:
        if candidate in lowered and lowered[candidate]:
            result["material"] = lowered[candidate]
            return

    # 2. Fallback: любой ключ, содержащий "матери" (материал, материалы,
    # материал верха и т.п.) - берём первый непустой.
    for key, value in specs.items():
        if "матери" in key.lower() and value:
            result["material"] = value
            return


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

    Ищем ТОЛЬКО внутри data-widget="webCharacteristics" (или
    webShortCharacteristics как fallback) - это стабильный атрибут,
    который Ozon не хэширует (в отличие от CSS-классов). Без этого
    ограничения dl/dt могли бы найтись где угодно на странице -
    в блоке рекомендаций, в шапке и т.д.

    Внутри контейнера структура:
    <dl><dt><span>Название</span></dt><dd>Значение</dd></dl>
    Внутри dt может быть несколько вложенных span - берём весь
    текст dt целиком. Внутри dd иногда лежит иконка "скопировать"
    (для Артикула) - она не текстовая, get_text() её не подхватит.
    """
    specs = {}

    container = soup.find(attrs={"data-widget": "webCharacteristics"})
    if container is None:
        container = soup.find(attrs={"data-widget": "webShortCharacteristics"})

    if container is None:
        result["specs"] = specs
        result["specs_count"] = 0
        return

    for dl in container.find_all("dl"):
        dt = dl.find("dt")
        dd = dl.find("dd")
        if not dt or not dd:
            continue

        key = dt.get_text(strip=True).rstrip(":").strip()
        value = dd.get_text(strip=True)

        if key and value:
            specs[key] = value

    result["specs"] = specs
    result["specs_count"] = len(specs)


def _parse_breadcrumbs(soup: BeautifulSoup, result: dict) -> None:
    """
    Источник 3: хлебные крошки (data-widget="breadCrumbs").
    Структура стабильна и не содержит свободного текста:
    <ol><li><a><span>Категория</span></a></li>...</ol>
    Последним элементом иногда идёт не категория, а бренд/продавец -
    это не страшно: название бренда почти никогда не совпадёт со
    словарным названием товара, поэтому отдельно его не отфильтровываем.
    """
    container = soup.find(attrs={"data-widget": "breadCrumbs"})

    if container is None:
        result["breadcrumbs"] = []
        return

    items = []

    for link in container.find_all("a"):
        text = link.get_text(strip=True)
        if text:
            items.append(text)

    result["breadcrumbs"] = items


# Регулярка достаёт CDN-ссылку Ozon на изображение товара из srcset.
# Формат: https://ir.ozone.ru/s3/multimedia-<bucket>/[wc<size>/]<id>.jpg
# wc100/wc250/... - превью нужного размера, полноразмерная версия
# получается тем же URL без сегмента wc<N>/.
_IMAGE_URL_RE = re.compile(
    r"https://ir\.ozone\.ru/s3/multimedia-[^/\s\"]+/(?:wc\d+/)?[\w.-]+\.jpg"
)


def _to_full_size(url: str) -> str:
    return re.sub(r"/wc\d+/", "/", url)


def _parse_images(soup: BeautifulSoup, result: dict) -> None:
    """
    Источник 3: галерея изображений товара.

    Ищем ТОЛЬКО внутри data-widget="webGallery" - иначе регулярка
    находит картинки блока рекомендаций/отзывов дальше по странице
    (проверено: без этого ограничения на реальной странице находится
    60+ "изображений", из которых товару принадлежит только ~11).
    """
    images = []

    gallery = soup.find(attrs={"data-widget": "webGallery"})
    if gallery is None:
        result["images"] = images
        return

    seen = set()
    for img in gallery.find_all("img"):
        srcset = img.get("srcset", "")
        for match in _IMAGE_URL_RE.findall(srcset):
            full_url = _to_full_size(match)
            if full_url not in seen:
                seen.add(full_url)
                images.append(full_url)

    result["images"] = images


def parse_ozon_page(page) -> dict:
    """
    Интеграция с Playwright (sync API): берём HTML уже отрисованной
    страницы (page.content() отдаёт текущий DOM, включая всё, что
    дорисовал JS) и парсим его этим же кодом.
    """
    page.wait_for_selector(
        "[data-widget='webCharacteristics'], "
        "[data-widget='webGallery'], "
        "script[type='application/ld+json']",
        state="attached",
        timeout=15000,
    )
    html = page.content()
    return parse_ozon_html(html)


# Единый селектор для ожидания ЛЮБОГО признака готовой карточки товара.
# ВАЖНО: это ОДИН вызов wait_for_selector с CSS-объединением через
# запятую, а НЕ последовательный перебор селекторов в цикле. Playwright
# возвращает управление, как только появляется ХОТЯ БЫ ОДИН из них -
# в худшем случае ждём timeout один раз, а не N раз подряд (раньше тут
# был цикл по 3 селектора с отдельным таймаутом на каждый - в худшем
# случае 3x5с=15с впустую на один товар, и это же било по общей
# скорости параллельной обработки).
_READY_SELECTOR = (
    "[data-widget='webCharacteristics'], "
    "[data-widget='webGallery'], "
    "script[type='application/ld+json']"
)


async def parse_ozon_page_async(page, timeout=15000) -> dict:
    """
    Асинхронный разбор уже открытой страницы Ozon.

    ВАЖНО: таймаут ожидания селекторов НЕ считается фатальной ошибкой.
    У Ozon бывают карточки без доставки в регион / снятые с продажи -
    на такой странице нужных виджетов (webCharacteristics, webGallery,
    ld+json) может не быть ВООБЩЕ, это не гонка времени, а факт. Раньше
    в этом случае мы бросали исключение и весь товар пропускался
    целиком - хотя build_product_card() умеет подставить название
    товара из slug URL как fallback (card.slug), но до этого fallback
    дело просто не доходило.

    Теперь при таймауте мы не прерываем обработку, а пробуем всё равно
    забрать HTML как есть (там может не быть характеристик/описания,
    но build_product_card() возьмёт название из slug ссылки - товар
    хотя бы попадёт в классификацию, а не потеряется полностью).
    """
    selector_found = True

    try:
        await page.wait_for_selector(
            _READY_SELECTOR,
            state="attached",
            timeout=timeout,
        )
    except Exception:
        selector_found = False

        try:
            current_url = page.url
        except Exception:
            current_url = "<unknown>"

        try:
            title = await page.title()
        except Exception:
            title = "<unknown>"

        log.warning(
            "OZON SELECTOR TIMEOUT (не фатально, продолжаем с "
            "тем что есть): url=%s title=%s",
            current_url,
            title,
        )

    try:
        html = await page.content()
    except Exception:
        log.exception(
            "Не удалось получить content() страницы даже после "
            "таймаута селектора - страница, вероятно, недоступна"
        )
        html = ""

    # ======================================================
    # СИНХРОННЫЙ HTML PARSER НЕ ДОЛЖЕН БЛОКИРОВАТЬ
    # ASYNCIO EVENT LOOP
    # ======================================================
    data = await asyncio.to_thread(parse_ozon_html, html)

    # Последний резерв - специфично для редиректов на /search/,
    # когда даже <title> страницы не дал ничего полезного.
    if not data.get("title") and not data.get("description"):
        try:
            hint = extract_search_query_hint(page.url)
        except Exception:
            hint = ""

        if hint:
            data["title"] = hint
            data["description"] = hint
            log.info("OZON SEARCH HINT: использован text= из URL: %s", hint)

    data["selector_found"] = selector_found
    return data


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
    print("MATERIAL:", data["material"])
    print("IMAGES:", len(data["images"]))
    for u in data["images"]:
        print("  ", u)
    print()
    print(f"SPECS ({data['specs_count']}):")
    for k, v in data["specs"].items():
        print(f"  {k}: {v}")
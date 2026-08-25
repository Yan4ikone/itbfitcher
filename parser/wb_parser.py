import asyncio
import json
import logging
import re
from typing import Any, Optional

import aiohttp
import requests

log = logging.getLogger(__name__)


class WBParser:
    CARD_JSON_TIMEOUT = 10
    BASKET_MAX = 100

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        })
        self._basket_cache = {}
        self._recent_baskets = []

    async def parse_page(self, page, responses=None):
        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""

        nm_id = self._extract_nm_id(current_url)
        if not nm_id:
            print("[WB PARSER] NM ID НЕ НАЙДЕН")
            return await self._parse_dom_async(page)

        print(f"[WB PARSER] NM_ID={nm_id}")

        # 1. Уже перехваченный браузером JSON — самый приоритетный путь.
        data = self._find_product_in_responses(responses, nm_id)
        if data:
            result = self._parse_card_json(data)
            if result.get("title"):
                print("[WB PARSER] PRODUCT FOUND: NETWORK")
                return result

        # 2. Реальный card.json. Basket определяется и проверяется по nm_id.
        data = await self._fetch_card_json(nm_id)
        if data:
            result = self._parse_card_json(data)
            if result.get("title"):
                print("[WB PARSER] PRODUCT FOUND: CARD.JSON")
                return result

        print("[WB PARSER] CARD.JSON НЕ НАЙДЕН")
        print("[WB PARSER] FALLBACK -> DOM")
        return await self._parse_dom_async(page)

    async def _fetch_card_json(self, nm_id: int):
        nm_id = int(nm_id)
        vol = nm_id // 100000
        part = nm_id // 1000

        print(f"[WB PARSER] vol={vol} part={part}")

        def make_url(basket: int) -> str:
            return (
                f"https://basket-{basket:02d}.wbbasket.ru/"
                f"vol{vol}/part{part}/{nm_id}/info/ru/card.json"
            )

        async def fetch(session, basket):
            url = make_url(basket)
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        return None
                    try:
                        payload = await response.json(content_type=None)
                    except Exception:
                        return None
                    if not isinstance(payload, dict):
                        return None

                    # HTTP 200 недостаточно: проверяем, что JSON относится
                    # именно к запрошенному товару.
                    product = self._find_product_object(payload, nm_id)
                    if product is None:
                        return None
                    return basket, product
            except Exception:
                return None

        # Сначала cache/recent/guess — дешёвый путь.
        candidates = []

        def add_candidate(basket):
            try:
                basket = int(basket)
            except (TypeError, ValueError):
                return
            if 1 <= basket <= self.BASKET_MAX and basket not in candidates:
                candidates.append(basket)

        add_candidate(self._basket_cache.get(vol))
        guessed = self._basket_guess(vol)
        add_candidate(guessed)
        for delta in (-1, 1, -2, 2, -3, 3, -4, 4, -5, 5):
            add_candidate(guessed + delta)
        for basket in self._recent_baskets:
            add_candidate(basket)

        timeout = aiohttp.ClientTimeout(total=4, connect=1.5, sock_read=3)
        connector = aiohttp.TCPConnector(limit=20, ssl=False)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # Быстрые кандидаты последовательно, чтобы не создавать лишний
            # трафик для обычных карточек.
            for basket in candidates:
                result = await fetch(session, basket)
                if result:
                    return self._remember_basket(vol, result[0], result[1])

            # Если быстрый путь не сработал — полный probe 1..100.
            remaining = [b for b in range(1, self.BASKET_MAX + 1) if b not in candidates]
            tasks = [asyncio.create_task(fetch(session, basket)) for basket in remaining]

            try:
                for task in asyncio.as_completed(tasks):
                    result = await task
                    if not result:
                        continue
                    basket, product = result
                    for other in tasks:
                        if not other.done():
                            other.cancel()
                    return self._remember_basket(vol, basket, product)
            finally:
                await asyncio.gather(*tasks, return_exceptions=True)

        print(f"[WB PARSER] BASKET НЕ НАЙДЕН: vol={vol} nm_id={nm_id}")
        return None

    def _remember_basket(self, vol, basket, product):
        self._basket_cache[vol] = basket
        if basket in self._recent_baskets:
            self._recent_baskets.remove(basket)
        self._recent_baskets.insert(0, basket)
        del self._recent_baskets[8:]
        print(f"[WB PARSER] BASKET FOUND: {basket}")
        print(f"[WB PARSER] PRODUCT JSON FOUND: title={bool(self._parse_card_json(product).get('title'))}")
        return product

    @staticmethod
    def _extract_nm_id(url: str) -> Optional[int]:
        if not url:
            return None
        match = re.search(r"/catalog/(\d+)", url, re.IGNORECASE)
        if not match:
            match = re.search(r"/(\d+)/detail", url, re.IGNORECASE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except (ValueError, TypeError):
            return None

    def _basket_guess(self, vol):
        ranges = (
            (143, 1), (287, 2), (431, 3), (719, 4),
            (1007, 5), (1061, 6), (1115, 7), (1169, 8),
            (1313, 9), (1601, 10), (1655, 11), (1919, 12),
            (2045, 13),
        )
        for max_vol, basket in ranges:
            if vol <= max_vol:
                return basket
        return max(14, min(self.BASKET_MAX, (vol // 144) + 1))

    def _find_product_in_responses(self, responses, nm_id: int):
        if not responses:
            return None
        print(f"[WB PARSER] NETWORK RESPONSES: {len(responses)}")
        nm_str = str(nm_id)
        for response in responses:
            try:
                if not isinstance(response, dict):
                    continue
                url = str(response.get("url", ""))
                data = response.get("data")
                if nm_str not in url and "card.json" not in url and "product" not in url and "detail" not in url:
                    continue
                product = self._find_product_object(data, nm_id)
                if product:
                    print(f"[WB PARSER] NETWORK PRODUCT FOUND: {url}")
                    return product
            except Exception:
                continue
        print("[WB PARSER] NETWORK PRODUCT НЕ НАЙДЕН")
        return None

    def _find_product_object(self, obj: Any, nm_id: int):
        if isinstance(obj, dict):
            for key in ("nmId", "nm_id", "imtId", "id"):
                value = obj.get(key)
                if value is not None:
                    try:
                        if int(value) == int(nm_id):
                            return obj
                    except (ValueError, TypeError):
                        pass
            if (obj.get("imt_name") or obj.get("name") or obj.get("title")) and (
                "description" in obj or "options" in obj or "characteristics" in obj or "sizes" in obj
            ):
                return obj
            for value in obj.values():
                result = self._find_product_object(value, nm_id)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_product_object(item, nm_id)
                if result:
                    return result
        return None

    def _parse_card_json(self, product: dict) -> dict:
        title = product.get("imt_name") or product.get("name") or product.get("title") or product.get("goodsName") or ""
        description = product.get("description") or product.get("descriptionText") or ""
        specs = {}
        for options in (
            product.get("options"), product.get("characteristics"), product.get("params"),
            product.get("properties"), product.get("characteristicsFull"),
        ):
            self._extract_specs(options, specs)

        ignored = {
            "description", "descriptionText", "imt_name", "name", "title", "options",
            "characteristics", "params", "properties", "characteristicsFull", "photos", "images", "colors", "sizes",
        }
        for key, value in product.items():
            if key in ignored or not isinstance(value, (str, int, float)):
                continue
            value_str = str(value).strip()
            if not value_str or len(value_str) >= 500:
                continue
            if key.lower() in {"id", "nm_id", "nmid", "imt_id", "subject_id", "subject_root_id"}:
                continue
            specs.setdefault(str(key), value_str)

        raw_parts = [str(title).strip(), str(description).strip()]
        raw_parts.extend(f"{k}: {v}" for k, v in specs.items())
        raw_text = " ".join(x for x in raw_parts if x)
        return {
            "title": str(title).strip(),
            "description": str(description).strip(),
            "specs": specs,
            "raw_text": raw_text,
            "sections": {},
            "parser_log": [],
        }

    def _extract_specs(self, obj: Any, specs: dict):
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    key = item.get("name") or item.get("title") or item.get("key") or item.get("paramName")
                    value = item.get("value") or item.get("text") or item.get("description") or item.get("valueName")
                    if key and value:
                        if isinstance(value, list):
                            value = ", ".join(str(x) for x in value)
                        elif isinstance(value, dict):
                            value = json.dumps(value, ensure_ascii=False)
                        specs[str(key).strip()] = str(value).strip()
                    else:
                        self._extract_specs(item, specs)
        elif isinstance(obj, dict):
            key = obj.get("name") or obj.get("title") or obj.get("key") or obj.get("paramName")
            value = obj.get("value") or obj.get("text") or obj.get("description") or obj.get("valueName")
            if key and value:
                if isinstance(value, list):
                    value = ", ".join(str(x) for x in value)
                specs[str(key).strip()] = str(value).strip()
                return
            for child in obj.values():
                self._extract_specs(child, specs)

    async def _parse_dom_async(self, page):
        result = await page.evaluate("""
        () => {
            const clean = value => value ? String(value).replace(/\\s+/g, " ").trim() : "";
            let title = "";
            for (const selector of ["h1", "[data-testid='product-title']", "[class*='productTitle']", "[class*='ProductTitle']", "[class*='product-card__title']", "[class*='productCard__title']"]) {
                const el = document.querySelector(selector);
                if (el) { const value = clean(el.innerText || el.textContent); if (value) { title = value; break; } }
            }
            let description = "";
            for (const selector of ["[data-testid='product-description']", "[class*='description']", "[class*='Description']", "[class*='about']"]) {
                for (const el of document.querySelectorAll(selector)) {
                    const value = clean(el.innerText || el.textContent);
                    if (value.length > description.length) description = value;
                }
            }
            const specs = {};
            const addSpec = (key, value) => {
                key = clean(key).replace(/:$/, ""); value = clean(value);
                if (key && value && key.length <= 200 && value.length <= 2000) specs[key] = value;
            };
            document.querySelectorAll("dl").forEach(dl => {
                const dts = dl.querySelectorAll("dt"), dds = dl.querySelectorAll("dd");
                for (let i = 0; i < Math.min(dts.length, dds.length); i++) addSpec(dts[i].innerText || dts[i].textContent, dds[i].innerText || dds[i].textContent);
            });
            for (const selector of ["[class*='characteristic'] li", "[class*='Characteristic'] li", "[class*='characteristics'] li", "[class*='Characteristics'] li", "[class*='option'] li", "[class*='Option'] li", "[class*='parameter'] li", "[class*='Parameter'] li", "[class*='params'] li", "[class*='spec'] li", "[class*='Spec'] li"]) {
                document.querySelectorAll(selector).forEach(row => {
                    const spans = row.querySelectorAll("span");
                    if (spans.length >= 2) { addSpec(spans[0].innerText || spans[0].textContent, spans[1].innerText || spans[1].textContent); return; }
                    const match = clean(row.innerText || row.textContent).match(/^([^:]{1,100}):\s*(.+)$/);
                    if (match) addSpec(match[1], match[2]);
                });
            }
            return {title, description, specs, raw_text: clean(document.body ? document.body.innerText : "")};
        }
        """)
        if not isinstance(result, dict):
            result = {}
        print(f"[WB PARSER] DOM FALLBACK: title={bool(result.get('title'))} description={len(result.get('description', '') or '')} specs={len(result.get('specs', {}) or {})}")
        return result

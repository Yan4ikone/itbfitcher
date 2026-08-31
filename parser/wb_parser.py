import asyncio
import json
import logging
import re
from typing import Any, Optional

import aiohttp
import requests

log = logging.getLogger(__name__)


class WBParser:
    CARD_API_URL = "https://card.wb.ru/cards/v4/detail"
    UPSTREAMS_URL = "https://cdn.wbbasket.ru/api/v3/upstreams"
    CARD_JSON_TIMEOUT = 8
    BASKET_MAX = 60

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        })
        self._basket_cache = {}
        self._upstream_ranges = None
        self._upstream_lock = asyncio.Lock()

    async def parse_page(self, page, responses=None):
        try:
            url = page.url or ""
        except Exception:
            url = ""
        nm_id = self._extract_nm_id(url)
        if not nm_id:
            print("[WB PARSER] NM ID НЕ НАЙДЕН")
            return await self._parse_dom_async(page)
        print(f"[WB PARSER] nm_id={nm_id}")

        best = {}

        data = self._find_product_in_responses(responses, nm_id)
        if data:
            result = self._parse_card_json(data)
            best = self._merge_wb_result(best, result)
            if self._is_rich(best) and self._has_description(best):
                print(
                    f"[WB PARSER] nm_id={nm_id} PRODUCT FOUND: NETWORK "
                    "(описание + характеристики есть)"
                )
                return best

            if self._is_rich(best):
                print(
                    f"[WB PARSER] nm_id={nm_id} NETWORK: "
                    "характеристики есть, но описания нет -> "
                    "добираем CARD.JSON"
                )

        # card.wb.ru - быстрый и надёжный источник названия/цены/бренда,
        # НО он практически никогда не отдаёт характеристики/полное
        # описание товара (Характеристики/Описание с карточки WB лежат
        # в другом месте - см. CARD.JSON ниже). Поэтому даже если title
        # найден здесь, идём дальше и дообогащаем результат.
        product = await self._fetch_public_card_api(nm_id)

        if product:
            result = self._parse_card_api(product, nm_id)
            best = self._merge_wb_result(best, result)

            if (
                    self._is_rich(best)
                    and self._has_description(best)
            ):
                print(
                    f"[WB PARSER] nm_id={nm_id} "
                    "PRODUCT FOUND: CARD.API "
                    "(описание + характеристики есть)"
                )
                return best

            if self._is_rich(best):
                print(
                    f"[WB PARSER] nm_id={nm_id} "
                    "CARD.API: характеристики есть, "
                    "но описания нет -> добираем CARD.JSON"
                )
            else:
                print(
                    f"[WB PARSER] nm_id={nm_id} "
                    "CARD.API: недостаточно данных -> "
                    "добираем CARD.JSON"
                )
        # basket-XX.wbbasket.ru/.../card.json - вот тут реально лежат
        # характеристики (options/characteristics/params/properties/
        # characteristicsFull) и полное описание товара.
        data = await self._fetch_card_json(nm_id)
        if data:
            result = self._parse_card_json(data)
            best = self._merge_wb_result(best, result)
            if best.get("title"):
                status = "характеристики есть" if self._is_rich(best) else "характеристик всё ещё нет"
                print(f"[WB PARSER] nm_id={nm_id} PRODUCT FOUND: CARD.JSON ({status})")
                return best

        if best.get("title"):
            # Название нашли, характеристики - нет ни в одном источнике.
            # Лучше отдать частичный результат, чем терять и его тоже.
            print(f"[WB PARSER] nm_id={nm_id} характеристики не найдены ни в одном источнике, возвращаем частичный результат")
            return best

        print(f"[WB PARSER] nm_id={nm_id} CARD.JSON/API НЕ НАЙДЕН")
        print(f"[WB PARSER] nm_id={nm_id} FALLBACK -> DOM")
        return await self._parse_dom_async(page)

    @staticmethod
    def _has_description(result):
        """
        Проверяет, что у карточки действительно получено
        полноценное описание товара.
        Для классификации WB описание является обязательным,
        потому что именно там часто находятся:
        - материал;
        - состав;
        - назначение;
        - пол;
        - возраст;
        - особенности товара.
        """
        description = str(result.get("description") or "").strip()

        return len(description) >= 20

    @staticmethod
    def _is_rich(result):
        """Есть ли уже описание/характеристики, а не только название."""
        description = (result.get("description") or "").strip()
        specs = result.get("specs") or {}
        return bool(result.get("title")) and (len(description) > 20 or len(specs) >= 3)

    @staticmethod
    def _merge_wb_result(base, new):
        """Дополняет накопленный результат данными из нового источника,
        не затирая уже найденные (более ранний источник считается
        приоритетным при конфликте одного и того же ключа specs)."""
        if not base:
            merged = dict(new)
            merged["specs"] = dict(new.get("specs") or {})
        else:
            merged = dict(base)
            if not merged.get("title"):
                merged["title"] = new.get("title", "")
            if not (merged.get("description") or "").strip():
                merged["description"] = new.get("description", "")
            specs = dict(new.get("specs") or {})
            specs.update(merged.get("specs") or {})
            merged["specs"] = specs

        merged["raw_text"] = " ".join(filter(None, [
            merged.get("title", ""),
            merged.get("description", ""),
            *[f"{k}: {v}" for k, v in merged["specs"].items()],
        ])).strip()
        merged.setdefault("sections", {})
        merged.setdefault("parser_log", [])
        return merged


    async def _fetch_public_card_api(self, nm_id: int):
        """Fetch WB card API with retry + requests fallback.

        The API itself is known to return HTTP 200 for products that may be
        blocked by the Wildberries HTML antibot page. aiohttp can occasionally
        time out while a normal requests connection succeeds, so a timeout is
        not treated as a missing product.
        """
        nm_id = int(nm_id)
        params = {
            "appType": 1,
            "curr": "rub",
            "dest": -1257786,
            "spp": 30,
            "lang": "ru",
            "nm": str(nm_id),
        }
        headers = dict(self.session.headers)

        # Two short async attempts. Do not hammer WB with many parallel retries.
        timeout = aiohttp.ClientTimeout(total=7, connect=3, sock_connect=3, sock_read=5)
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(self.CARD_API_URL, params=params, headers=headers) as response:
                        if response.status != 200:
                            print(f"[WB PARSER] nm_id={nm_id} CARD.API HTTP {response.status} attempt={attempt + 1}")
                            break
                        payload = await response.json(content_type=None)
                        product = self._extract_card_api_product(payload, nm_id)
                        if product:
                            return product
                        print(f"[WB PARSER] nm_id={nm_id} CARD.API PRODUCT NOT FOUND")
                        return None
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                print(f"[WB PARSER] nm_id={nm_id} CARD.API RETRY: {type(exc).__name__} attempt={attempt + 1}")
            except Exception as exc:
                print(f"[WB PARSER] nm_id={nm_id} CARD.API ERROR: {type(exc).__name__}: {exc}")
                break

        # Important: the same request works from a normal requests client in
        # the user's environment. Use it as a transport fallback, not another
        # product-specific workaround.
        try:
            response = await asyncio.to_thread(
                requests.get,
                self.CARD_API_URL,
                params=params,
                headers=headers,
                timeout=(5, 12),
            )
            if response.status_code == 200:
                payload = response.json()
                product = self._extract_card_api_product(payload, nm_id)
                if product:
                    print(f"[WB PARSER] nm_id={nm_id} PRODUCT FOUND: CARD.API/REQUESTS")
                    return product
            else:
                print(f"[WB PARSER] nm_id={nm_id} CARD.API/REQUESTS HTTP {response.status_code}")
        except Exception as exc:
            print(f"[WB PARSER] nm_id={nm_id} CARD.API/REQUESTS ERROR: {type(exc).__name__}: {exc}")
        return None

    @staticmethod
    def _extract_card_api_product(payload, nm_id: int):
        if not isinstance(payload, dict):
            return None
        products = payload.get("products")
        if not isinstance(products, list):
            data = payload.get("data")
            products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            return None
        target = int(nm_id)
        for product in products:
            if not isinstance(product, dict):
                continue
            try:
                if int(product.get("id")) == target:
                    return product
            except (TypeError, ValueError):
                continue
        return None

    def _parse_card_api(self, product: dict, nm_id: int) -> dict:
        title = str(product.get("name") or product.get("imt_name") or product.get("title") or "").strip()
        description = str(product.get("description") or "").strip()
        specs = {}
        skip = {"name", "imt_name", "title", "description", "sizes", "colors", "photos", "pics", "tags"}
        for key, value in product.items():
            if key in skip:
                continue
            if isinstance(value, (str, int, float)) and str(value).strip():
                specs.setdefault(str(key), str(value).strip())
        if product.get("brand"):
            specs.setdefault("brand", str(product["brand"]).strip())
        raw = " ".join([title, description] + [f"{k}: {v}" for k, v in specs.items()]).strip()
        return {"title": title, "description": description, "specs": specs, "raw_text": raw, "sections": {}, "parser_log": [], "nm_id": nm_id}

    async def _load_upstream_ranges(self):
        if self._upstream_ranges is not None:
            return self._upstream_ranges
        async with self._upstream_lock:
            if self._upstream_ranges is not None:
                return self._upstream_ranges
            try:
                timeout = aiohttp.ClientTimeout(total=5, connect=2, sock_read=3)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(self.UPSTREAMS_URL, headers={"User-Agent": self.session.headers["User-Agent"], "Accept": "application/json,*/*"}) as response:
                        if response.status == 200:
                            payload = await response.json(content_type=None)
                            parsed = []
                            for route in payload.get("origin", {}).get("mediabasket_route_map", []):
                                for item in route.get("hosts", []):
                                    try:
                                        parsed.append((int(item["vol_range_from"]), int(item["vol_range_to"]), self._basket_from_host(item.get("host", ""))))
                                    except (KeyError, TypeError, ValueError):
                                        pass
                            if parsed:
                                self._upstream_ranges = parsed
                                print(f"[WB PARSER] UPSTREAMS: loaded {len(parsed)} ranges")
                                return parsed
            except Exception as exc:
                print(f"[WB PARSER] UPSTREAMS ERROR: {type(exc).__name__}: {exc}")
            self._upstream_ranges = []
            return self._upstream_ranges

    @staticmethod
    def _basket_from_host(host: str) -> int:
        match = re.search(r"basket-(\d+)", host or "")
        if not match:
            raise ValueError("basket host not found")
        return int(match.group(1))

    async def _fetch_card_json(self, nm_id: int):
        nm_id = int(nm_id)
        vol = nm_id // 100000
        part = nm_id // 1000
        print(f"[WB PARSER] nm_id={nm_id} vol={vol} part={part}")
        def make_url(basket):
            return f"https://basket-{basket:02d}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
        candidates = []
        def add(value):
            try:
                value = int(value)
            except (TypeError, ValueError):
                return
            if 1 <= value <= self.BASKET_MAX and value not in candidates:
                candidates.append(value)
        add(self._basket_cache.get(vol))
        ranges = await self._load_upstream_ranges()
        for start, end, basket in ranges:
            if start <= vol <= end:
                add(basket)
                break
        add(self._basket_guess(vol))
        for base in list(candidates):
            add(base - 1)
            add(base + 1)

        timeout = aiohttp.ClientTimeout(total=self.CARD_JSON_TIMEOUT, connect=3, sock_read=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for basket in candidates:
                try:
                    async with session.get(make_url(basket), headers={"User-Agent": self.session.headers["User-Agent"], "Accept": "application/json,text/plain,*/*"}) as response:
                        if response.status != 200:
                            continue
                        data = await response.json(content_type=None)
                        if isinstance(data, dict) and data:
                            self._basket_cache[vol] = basket
                            print(f"[WB PARSER] nm_id={nm_id} BASKET FOUND: {basket}")
                            return data
                except Exception:
                    continue
        print(f"[WB PARSER] nm_id={nm_id} BASKET НЕ НАЙДЕН: vol={vol}")
        return None

    def _basket_guess(self, vol):
        # Only a fallback hint. New vol values never require editing this list
        # because Card API is the primary source.
        ranges = ((143,1),(287,2),(431,3),(719,4),(1007,5),(1169,8),(1601,10),(1919,12),(2405,15),(3053,18),(3701,21),(4349,24),(4877,26),(5501,28),(6125,30),(6749,32),(7373,34),(7997,36),(8741,38),(9173,39),(9605,40),(10373,41),(11909,43),(13445,45),(14981,47),(16517,49),(18053,51),(18821,52))
        for maximum, basket in ranges:
            if vol <= maximum:
                return basket
        return 52

    @staticmethod
    def _extract_nm_id(url: str) -> Optional[int]:
        match = re.search(r"/catalog/(\d+)", url or "", re.I) or re.search(r"/(\d+)/detail", url or "", re.I)
        try:
            return int(match.group(1)) if match else None
        except (TypeError, ValueError):
            return None

    def _find_product_in_responses(self, responses, nm_id):
        if not responses:
            return None
        for response in responses:
            if not isinstance(response, dict):
                continue
            product = self._find_product_object(response, nm_id)
            if product:
                return product
        return None

    def _find_product_object(self, obj: Any, nm_id: int):
        if isinstance(obj, dict):
            for key in ("nmId", "nm_id", "imtId", "id"):
                try:
                    if obj.get(key) is not None and int(obj.get(key)) == int(nm_id):
                        return obj
                except (TypeError, ValueError):
                    pass
            for value in obj.values():
                found = self._find_product_object(value, nm_id)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = self._find_product_object(item, nm_id)
                if found:
                    return found
        return None

    def _parse_card_json(self, product: dict) -> dict:
        title = product.get("imt_name") or product.get("name") or product.get("title") or product.get("goodsName") or ""
        description = product.get("description") or product.get("descriptionText") or ""
        specs = {}
        for value in (product.get("options"), product.get("characteristics"), product.get("params"), product.get("properties"), product.get("characteristicsFull")):
            self._extract_specs(value, specs)
        ignored = {"description","descriptionText","imt_name","name","title","options","characteristics","params","properties","characteristicsFull","photos","images","colors","sizes"}
        for key, value in product.items():
            if key not in ignored and isinstance(value, (str,int,float)) and str(value).strip() and len(str(value)) < 500:
                specs.setdefault(str(key), str(value).strip())
        raw = " ".join([str(title).strip(), str(description).strip()] + [f"{k}: {v}" for k,v in specs.items()]).strip()
        return {"title": str(title).strip(), "description": str(description).strip(), "specs": specs, "raw_text": raw, "sections": {}, "parser_log": []}

    def _extract_specs(self, obj, specs):
        if isinstance(obj, list):
            for item in obj:
                self._extract_specs(item, specs)
        elif isinstance(obj, dict):
            key = obj.get("name") or obj.get("title") or obj.get("key") or obj.get("paramName")
            value = obj.get("value") or obj.get("text") or obj.get("description") or obj.get("valueName")
            if key and value:
                if isinstance(value, list): value = ", ".join(map(str, value))
                elif isinstance(value, dict): value = json.dumps(value, ensure_ascii=False)
                specs[str(key).strip()] = str(value).strip()
            else:
                for child in obj.values(): self._extract_specs(child, specs)

    async def _parse_dom_async(self, page):
        result = await page.evaluate("""
        () => {
            const clean = v => v ? String(v).replace(/\\s+/g, ' ').trim() : '';
            let title = '';
            for (const selector of ['h1', '[data-testid="product-title"]', '[class*="productTitle"]', '[class*="ProductTitle"]']) {
                const el = document.querySelector(selector);
                if (el) { const v = clean(el.innerText || el.textContent); if (v) { title = v; break; } }
            }
            let description = '';
            for (const selector of ['[data-testid="product-description"]', '[class*="description"]', '[class*="Description"]', '[class*="about"]']) {
                for (const el of document.querySelectorAll(selector)) { const v = clean(el.innerText || el.textContent); if (v.length > description.length) description = v; }
            }
            const specs = {};
            return {title, description, specs, raw_text: clean(document.body ? document.body.innerText : '')};
        }
        """)
        if not isinstance(result, dict): result = {}
        print(f"[WB PARSER] DOM FALLBACK: title={bool(result.get('title'))} description={len(result.get('description','') or '')} specs={len(result.get('specs',{}) or {})}")
        return result
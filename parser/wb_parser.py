import json
import logging
import re
from typing import Any, Optional

import requests

log = logging.getLogger(__name__)


class WBParser:

    CARD_JSON_TIMEOUT = 10

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

    # ==========================================================
    # PUBLIC
    # ==========================================================

    async def parse_page(self, page, responses=None):

        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""

        nm_id = self._extract_nm_id(current_url)

        if not nm_id:
            print("[WB PARSER] NM ID НЕ НАЙДЕН")
            return await self._parse_dom_async(page)

        data = self._find_product_in_responses(
            responses,
            nm_id,
        )

        if data:
            result = self._parse_card_json(data)

            if result.get("title"):
                return result

        # ======================================================
        # ОСНОВНОЙ ПУТЬ WB
        # ======================================================

        data = await self._fetch_card_json(nm_id)

        if data:

            result = self._parse_card_json(data)

            if result.get("title"):
                return result

        # ======================================================
        # ПОСЛЕДНИЙ FALLBACK
        # ======================================================

        print("[WB PARSER] CARD.JSON НЕ НАЙДЕН")
        print("[WB PARSER] FALLBACK -> DOM")

        return await self._parse_dom_async(page)

    async def _fetch_card_json(self, nm_id: int):
        """
        Быстрый и надёжный поиск WB card.json.

        Алгоритм:

            1. cache по vol
            2. несколько вероятных basket
            3. если не нашли — параллельный probe 1..60
            4. найденный basket сохраняем в cache

        ВАЖНО:
        basket считается найденным ТОЛЬКО если настоящий card.json
        вернул HTTP 200 и корректный JSON.

        Никаких HEAD.
        Никаких 404 -> FOUND.
        Никаких ожиданий страницы.
        """

        import aiohttp
        import asyncio

        nm_id = int(nm_id)

        vol = nm_id // 100000
        part = nm_id // 1000

        print(
            f"[WB PARSER] vol={vol} part={part}"
        )

        # ==========================================================
        # CARD URL
        # ==========================================================

        def make_url(basket: int) -> str:
            return (
                f"https://basket-{basket}.wbbasket.ru/"
                f"vol{vol}/part{part}/{nm_id}/info/ru/card.json"
            )

        # ==========================================================
        # 1. CACHE
        # ==========================================================

        cached = self._basket_cache.get(vol)

        if cached:
            url = make_url(cached)

            try:
                timeout = aiohttp.ClientTimeout(
                    total=3,
                    connect=1.5,
                    sock_read=2,
                )

                async with aiohttp.ClientSession(
                        timeout=timeout
                ) as session:

                    async with session.get(
                            url,
                            headers={
                                "User-Agent": (
                                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                        "AppleWebKit/537.36 "
                                        "(KHTML, like Gecko) "
                                        "Chrome/151.0.0.0 Safari/537.36"
                                ),
                                "Accept": "application/json,text/plain,*/*",
                            },
                    ) as response:

                        if response.status == 200:

                            try:
                                data = await response.json(
                                    content_type=None
                                )

                                if isinstance(data, dict):
                                    return data

                            except Exception:
                                pass

            except Exception:
                pass

            # Cache устарел.
            self._basket_cache.pop(
                vol,
                None,
            )

        # ==========================================================
        # 2. КАНДИДАТЫ
        # ==========================================================

        candidates = []

        def add_candidate(basket):
            if not isinstance(basket, int):
                return

            if not 1 <= basket <= 60:
                return

            if basket not in candidates:
                candidates.append(basket)

        # ----------------------------------------------------------
        # Известный guess
        # ----------------------------------------------------------

        guessed = self._basket_guess(vol)

        add_candidate(guessed)

        # ----------------------------------------------------------
        # Соседи
        # ----------------------------------------------------------

        for delta in (
                -1,
                1,
                -2,
                2,
                -3,
                3,
        ):
            add_candidate(
                guessed + delta
            )

        # ----------------------------------------------------------
        # Недавно найденные basket
        # ----------------------------------------------------------

        for basket in self._recent_baskets:
            add_candidate(basket)

        # ==========================================================
        # 3. Сначала пробуем кандидатов ПОСЛЕДОВАТЕЛЬНО
        #
        # Это дешёвая часть.
        # В большинстве случаев basket находится здесь.
        # ==========================================================

        timeout = aiohttp.ClientTimeout(
            total=3,
            connect=1.5,
            sock_read=2,
        )

        try:

            connector = aiohttp.TCPConnector(
                limit=10,
                ssl=False,
            )

            async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
            ) as session:

                for basket in candidates:

                    url = make_url(basket)

                    try:

                        async with session.get(
                                url,
                                headers={
                                    "User-Agent": (
                                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                            "AppleWebKit/537.36 "
                                            "(KHTML, like Gecko) "
                                            "Chrome/151.0.0.0 Safari/537.36"
                                    ),
                                    "Accept": (
                                            "application/json,"
                                            "text/plain,*/*"
                                    ),
                                },
                        ) as response:

                            if response.status != 200:
                                continue

                            try:
                                data = await response.json(
                                    content_type=None
                                )
                            except Exception:
                                continue

                            if not isinstance(data, dict):
                                continue

                            # ==================================================
                            # FOUND
                            # ==================================================

                            self._basket_cache[vol] = basket

                            if basket in self._recent_baskets:
                                self._recent_baskets.remove(
                                    basket
                                )

                            self._recent_baskets.insert(
                                0,
                                basket,
                            )

                            del self._recent_baskets[8:]

                            print(
                                f"[WB PARSER] BASKET FOUND: "
                                f"{basket}"
                            )

                            print(
                                f"[WB PARSER] CARD.JSON: "
                                f"{url}"
                            )

                            return data

                    except Exception:
                        continue

                # ==========================================================
                # 4. FULL PROBE
                #
                # Только если быстрые кандидаты не сработали.
                #
                # Проверяем РЕАЛЬНЫЙ card.json.
                # ==========================================================

                remaining = [
                    basket
                    for basket in range(1, 61)
                    if basket not in candidates
                ]

                async def probe(basket):

                    url = make_url(basket)

                    try:

                        async with session.get(
                                url,
                                headers={
                                    "User-Agent": (
                                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                            "AppleWebKit/537.36 "
                                            "(KHTML, like Gecko) "
                                            "Chrome/151.0.0.0 Safari/537.36"
                                    ),
                                    "Accept": (
                                            "application/json,"
                                            "text/plain,*/*"
                                    ),
                                },
                        ) as response:

                            # ВАЖНО:
                            # только 200 означает найденный basket.
                            if response.status != 200:
                                return None

                            try:
                                data = await response.json(
                                    content_type=None
                                )
                            except Exception:
                                return None

                            if not isinstance(data, dict):
                                return None

                            return basket, data

                    except Exception:
                        return None

                tasks = [
                    asyncio.create_task(
                        probe(basket)
                    )
                    for basket in remaining
                ]

                for task in asyncio.as_completed(tasks):

                    result = await task

                    if result is None:
                        continue

                    basket, data = result

                    # ======================================================
                    # Нашли.
                    # ======================================================

                    self._basket_cache[vol] = basket

                    if basket in self._recent_baskets:
                        self._recent_baskets.remove(
                            basket
                        )

                    self._recent_baskets.insert(
                        0,
                        basket,
                    )

                    del self._recent_baskets[8:]

                    print(
                        f"[WB PARSER] BASKET FOUND: "
                        f"{basket}"
                    )

                    print(
                        f"[WB PARSER] CARD.JSON: "
                        f"{make_url(basket)}"
                    )

                    # Отменяем остальные probe.
                    for other in tasks:
                        if not other.done():
                            other.cancel()

                    return data

        except Exception as exc:

            print(
                f"[WB PARSER] CARD.JSON SEARCH ERROR: "
                f"{type(exc).__name__}: {exc}"
            )

        print(
            f"[WB PARSER] BASKET НЕ НАЙДЕН: "
            f"vol={vol}"
        )

        return None

    # ==========================================================
    # NM ID
    # ==========================================================

    @staticmethod
    def _extract_nm_id(url: str) -> Optional[int]:

        if not url:
            return None

        match = re.search(
            r"/catalog/(\d+)",
            url,
            re.IGNORECASE,
        )

        if not match:
            match = re.search(
                r"/(\d+)/detail",
                url,
                re.IGNORECASE,
            )

        if not match:
            return None

        try:
            return int(match.group(1))
        except (ValueError, TypeError):
            return None

    # ==========================================================
    # BASKET
    # ==========================================================

    def _basket_guess(self, vol):
        """
        Быстрая оценка basket по vol.

        WB распределяет vol по диапазонам.
        Это НЕ источник истины, поэтому результат обязательно
        проверяется реальным card.json.

        Формула используется только как быстрый первый кандидат.
        """

        # Основные диапазоны WB.
        #
        # Эти границы соответствуют актуальной схеме распределения
        # старых/основных vol по basket.
        ranges = (
            (143, 1),
            (287, 2),
            (431, 3),
            (719, 4),
            (1007, 5),
            (1061, 6),
            (1115, 7),
            (1169, 8),
            (1313, 9),
            (1601, 10),
            (1655, 11),
            (1919, 12),
            (2045, 13),
            (2189, 14),
            (2405, 15),
            (2621, 16),
            (2837, 17),
            (3053, 18),
            (3269, 19),
            (3485, 20),
            (3701, 21),
            (3917, 22),
            (4133, 23),
            (4349, 24),
            (4565, 25),
            (4877, 26),
            (5189, 27),
            (5501, 28),
            (5813, 29),
            (6125, 30),
            (6437, 31),
            (6749, 32),
            (7061, 33),
            (7373, 34),
            (7685, 35),
            (7997, 36),
            (8309, 37),
            (8741, 38),
            (9173, 39),
            (9605, 40),
            (10373, 41),
            (11141, 42),
            (11909, 43),
            (12677, 44),
            (13445, 45),
            (14213, 46),
            (14981, 47),
            (15749, 48),
            (16517, 49),
            (17285, 50),
            (18053, 51),
            (18821, 52),
        )

        for max_vol, basket in ranges:
            if vol <= max_vol:
                return basket

        # Для новых диапазонов приблизительная оценка.
        return max(
            14,
            min(
                60,
                (vol // 144) + 1,
            ),
        )

    def _card_json_url(self, nm_id, basket):
        vol = nm_id // 100000
        part = nm_id // 1000

        return (
            f"https://basket-{basket:02d}.wbbasket.ru/"
            f"vol{vol}/part{part}/{nm_id}/info/ru/card.json"
        )

    def _get_card_json_fast(self, nm_id):
        """
        Максимально быстрый поиск card.json.

        Порядок:

            1. cache для vol
            2. cache для самого nm_id
            3. быстрый basket guess
            4. несколько соседних basket
            5. recent baskets

        Никаких больших all-poo JSON.
        """

        vol = nm_id // 100000

        # ==================================================
        # 1. CACHE VOL
        # ==================================================

        cached_basket = self._basket_cache.get(vol)

        if cached_basket:

            url = self._card_json_url(
                nm_id,
                cached_basket,
            )

            data = self._get_json(
                url,
                print_status=False,
            )

            if data:
                return data, cached_basket

            # Если basket перестал работать —
            # удаляем старое значение.
            self._basket_cache.pop(
                vol,
                None,
            )

        # ==================================================
        # 2. ПЕРВЫЙ КАНДИДАТ
        # ==================================================

        guessed = self._basket_guess(vol)

        candidates = []

        def add_candidate(basket):

            if not 1 <= basket <= 60:
                return

            if basket not in candidates:
                candidates.append(basket)

        add_candidate(guessed)

        # ==================================================
        # 3. СОСЕДНИЕ BASKET
        # ==================================================

        # Обычно правильный basket находится очень близко
        # к расчётному.
        for delta in (
                -1,
                1,
                -2,
                2,
                -3,
                3,
        ):
            add_candidate(
                guessed + delta
            )

        # ==================================================
        # 4. RECENT
        # ==================================================

        for basket in self._recent_baskets:
            add_candidate(basket)

        # ==================================================
        # 5. ПРОВЕРКА
        # ==================================================

        for basket in candidates:

            url = self._card_json_url(
                nm_id,
                basket,
            )

            data = self._get_json(
                url,
                print_status=False,
            )

            if not data:
                continue

            # Нашли.
            self._basket_cache[vol] = basket

            if basket in self._recent_baskets:
                self._recent_baskets.remove(
                    basket
                )

            self._recent_baskets.insert(
                0,
                basket,
            )

            # Не раздуваем список.
            del self._recent_baskets[8:]

            return data, basket

        return None, None

    def _search_basket_in_object(
        self,
        obj: Any,
        vol: int,
    ) -> Optional[int]:

        target = str(vol)

        if isinstance(obj, dict):

            for key, value in obj.items():

                key_str = str(key)

                # Возможные варианты:
                # "7315": 34
                # "7315": "34"
                # vol -> basket
                if key_str == target:

                    basket = self._normalize_basket(value)

                    if basket:
                        return basket

                # Иногда структура глубже.
                result = self._search_basket_in_object(
                    value,
                    vol,
                )

                if result:
                    return result

        elif isinstance(obj, list):

            for item in obj:

                result = self._search_basket_in_object(
                    item,
                    vol,
                )

                if result:
                    return result

        return None

    @staticmethod
    def _normalize_basket(value: Any) -> Optional[int]:

        if isinstance(value, int):
            if 1 <= value <= 100:
                return value

        if isinstance(value, str):

            match = re.search(
                r"(\d+)",
                value,
            )

            if match:
                number = int(match.group(1))

                if 1 <= number <= 100:
                    return number

        if isinstance(value, dict):

            for key in (
                "basket",
                "basketNumber",
                "basket_num",
                "basket_id",
                "id",
            ):
                if key in value:
                    result = WBParser._normalize_basket(
                        value[key]
                    )

                    if result:
                        return result

        return None

    # ==========================================================
    # JSON REQUEST
    # ==========================================================

    def _get_json(
            self,
            url,
            print_status=True,
    ):
        try:

            response = self.session.get(
                url,
                timeout=3,
            )

            if print_status:
                print(
                    f"[WB PARSER] CARD.JSON STATUS: "
                    f"{response.status_code}"
                )

            if response.status_code != 200:
                return None

            return response.json()

        except (
                requests.RequestException,
                ValueError,
        ):
            return None

        except Exception:
            return None

    # ==========================================================
    # NETWORK RESPONSES
    # ==========================================================

    def _find_product_in_responses(
        self,
        responses,
        nm_id: int,
    ):

        if not responses:
            return None

        print(
            f"[WB PARSER] NETWORK RESPONSES: "
            f"{len(responses)}"
        )

        nm_str = str(nm_id)

        for response in responses:

            try:

                if isinstance(response, dict):

                    url = str(
                        response.get("url", "")
                    )

                    data = response.get("data")

                else:

                    continue

                # Только потенциально полезные ответы.
                if (
                    "card.json" not in url
                    and nm_str not in url
                    and "detail" not in url
                    and "product" not in url
                ):
                    continue

                product = self._find_product_object(
                    data,
                    nm_id,
                )

                if product:
                    return product

            except Exception:
                continue

        print(
            "[WB PARSER] NETWORK PRODUCT НЕ НАЙДЕН"
        )

        return None

    def _find_product_object(
        self,
        obj: Any,
        nm_id: int,
    ):

        if isinstance(obj, dict):

            # Самый надёжный вариант.
            for key in (
                "nmId",
                "nm_id",
                "imtId",
                "id",
            ):

                value = obj.get(key)

                if value is not None:

                    try:
                        if int(value) == int(nm_id):
                            return obj
                    except (ValueError, TypeError):
                        pass

            # Если объект явно карточка.
            if (
                obj.get("imt_name")
                or obj.get("name")
                or obj.get("title")
            ):
                if (
                    "description" in obj
                    or "options" in obj
                    or "characteristics" in obj
                    or "sizes" in obj
                ):
                    return obj

            for value in obj.values():

                result = self._find_product_object(
                    value,
                    nm_id,
                )

                if result:
                    return result

        elif isinstance(obj, list):

            for item in obj:

                result = self._find_product_object(
                    item,
                    nm_id,
                )

                if result:
                    return result

        return None

    # ==========================================================
    # CARD.JSON PARSER
    # ==========================================================

    def _parse_card_json(self, product: dict) -> dict:

        title = (
            product.get("imt_name")
            or product.get("name")
            or product.get("title")
            or product.get("goodsName")
            or ""
        )

        description = (
            product.get("description")
            or product.get("descriptionText")
            or ""
        )

        specs = {}

        # ------------------------------------------------------
        # characteristics / options / params
        # ------------------------------------------------------

        candidates = [
            product.get("options"),
            product.get("characteristics"),
            product.get("params"),
            product.get("properties"),
            product.get("characteristicsFull"),
        ]

        for options in candidates:

            self._extract_specs(
                options,
                specs,
            )

        # ------------------------------------------------------
        # Дополнительные поля card.json
        # ------------------------------------------------------

        ignored = {
            "description",
            "descriptionText",
            "imt_name",
            "name",
            "title",
            "options",
            "characteristics",
            "params",
            "properties",
            "characteristicsFull",
            "photos",
            "images",
            "colors",
            "sizes",
        }

        for key, value in product.items():

            if key in ignored:
                continue

            if isinstance(value, (str, int, float)):

                value_str = str(value).strip()

                if not value_str:
                    continue

                # Служебные поля не нужны в характеристиках.
                if key.lower() in {
                    "id",
                    "nm_id",
                    "nmid",
                    "imt_id",
                    "subject_id",
                    "subject_root_id",
                }:
                    continue

                if len(value_str) < 500:
                    specs.setdefault(
                        str(key),
                        value_str,
                    )

        # ------------------------------------------------------
        # raw_text
        # ------------------------------------------------------

        raw_parts = []

        if title:
            raw_parts.append(str(title))

        if description:
            raw_parts.append(str(description))

        for key, value in specs.items():

            raw_parts.append(
                f"{key}: {value}"
            )

        raw_text = " ".join(
            part.strip()
            for part in raw_parts
            if part
        )

        return {
            "title": str(title).strip(),
            "description": str(description).strip(),
            "specs": specs,
            "raw_text": raw_text,
            "sections": {},
            "parser_log": [],
        }

    def _extract_specs(
        self,
        obj: Any,
        specs: dict,
    ):

        if isinstance(obj, list):

            for item in obj:

                if isinstance(item, dict):

                    key = (
                        item.get("name")
                        or item.get("title")
                        or item.get("key")
                        or item.get("paramName")
                    )

                    value = (
                        item.get("value")
                        or item.get("text")
                        or item.get("description")
                        or item.get("valueName")
                    )

                    if key and value:

                        if isinstance(value, list):

                            value = ", ".join(
                                str(x)
                                for x in value
                            )

                        elif isinstance(value, dict):

                            value = json.dumps(
                                value,
                                ensure_ascii=False,
                            )

                        specs[str(key).strip()] = (
                            str(value).strip()
                        )

                    else:
                        self._extract_specs(
                            item,
                            specs,
                        )

                elif isinstance(item, str):
                    continue

        elif isinstance(obj, dict):

            # Частый формат:
            #
            # {
            #   "name": "...",
            #   "value": "..."
            # }

            key = (
                obj.get("name")
                or obj.get("title")
                or obj.get("key")
                or obj.get("paramName")
            )

            value = (
                obj.get("value")
                or obj.get("text")
                or obj.get("description")
                or obj.get("valueName")
            )

            if key and value:

                if isinstance(value, list):

                    value = ", ".join(
                        str(x)
                        for x in value
                    )

                specs[str(key).strip()] = (
                    str(value).strip()
                )

                return

            for child in obj.values():

                self._extract_specs(
                    child,
                    specs,
                )

    # ==========================================================
    # DOM FALLBACK
    # ==========================================================

    async def _parse_dom_async(self, page):
        """
        Последний fallback для WB.

        ВАЖНО:
        page работает через playwright.async_api,
        поэтому здесь НЕ используем locator.inner_text()
        и locator.count() без await.

        Основной способ — один page.evaluate().
        Это быстрее и не создаёт десятки Playwright-вызовов.
        """

        result = await page.evaluate("""
        () => {

            const clean = (value) => {
                if (!value) return "";
                return String(value)
                    .replace(/\\\\s+/g, " ")
                    .trim();
            };

            // -----------------------------------------------
            // TITLE
            // -----------------------------------------------

            let title = "";

            const titleSelectors = [
                "h1",
                "[data-testid='product-title']",
                "[class*='productTitle']",
                "[class*='ProductTitle']",
                "[class*='product-card__title']",
                "[class*='productCard__title']"
            ];

            for (const selector of titleSelectors) {

                const el = document.querySelector(selector);

                if (el) {
                    const value = clean(el.innerText || el.textContent);

                    if (value) {
                        title = value;
                        break;
                    }
                }
            }

            // -----------------------------------------------
            // DESCRIPTION
            // -----------------------------------------------

            let description = "";

            const descriptionSelectors = [
                "[data-testid='product-description']",
                "[class*='description']",
                "[class*='Description']",
                "[class*='about']"
            ];

            for (const selector of descriptionSelectors) {

                const elements = document.querySelectorAll(selector);

                for (const el of elements) {

                    const value = clean(
                        el.innerText || el.textContent
                    );

                    if (value && value.length > description.length) {
                        description = value;
                    }
                }
            }

            // -----------------------------------------------
            // CHARACTERISTICS
            // -----------------------------------------------

            const specs = {};

            const addSpec = (key, value) => {

                key = clean(key).replace(/:$/, "");
                value = clean(value);

                if (!key || !value) return;

                // Не записываем очевидный мусор
                if (key.length > 200) return;
                if (value.length > 2000) return;

                specs[key] = value;
            };

            // -----------------------------------------------
            // dl / dt / dd
            // -----------------------------------------------

            document.querySelectorAll("dl").forEach(dl => {

                const dts = dl.querySelectorAll("dt");
                const dds = dl.querySelectorAll("dd");

                const count = Math.min(
                    dts.length,
                    dds.length
                );

                for (let i = 0; i < count; i++) {

                    addSpec(
                        dts[i].innerText || dts[i].textContent,
                        dds[i].innerText || dds[i].textContent
                    );
                }
            });

            // -----------------------------------------------
            // li / rows
            // -----------------------------------------------

            const rowSelectors = [
                "[class*='characteristic'] li",
                "[class*='Characteristic'] li",
                "[class*='characteristics'] li",
                "[class*='Characteristics'] li",
                "[class*='option'] li",
                "[class*='Option'] li",
                "[class*='parameter'] li",
                "[class*='Parameter'] li",
                "[class*='params'] li",
                "[class*='spec'] li",
                "[class*='Spec'] li"
            ];

            for (const selector of rowSelectors) {

                document.querySelectorAll(selector).forEach(row => {

                    const spans = row.querySelectorAll("span");

                    if (spans.length >= 2) {

                        addSpec(
                            spans[0].innerText || spans[0].textContent,
                            spans[1].innerText || spans[1].textContent
                        );

                        return;
                    }

                    const text = clean(
                        row.innerText || row.textContent
                    );

                    if (!text) return;

                    const match = text.match(
                        /^([^:]{1,100}):\\s*(.+)$/
                    );

                    if (match) {
                        addSpec(
                            match[1],
                            match[2]
                        );
                    }
                });
            }

            // -----------------------------------------------
            // DATA-TESTID / common WB blocks
            // -----------------------------------------------

            document.querySelectorAll(
                "[data-testid]"
            ).forEach(el => {

                const testid = (
                    el.getAttribute("data-testid") || ""
                ).toLowerCase();

                if (
                    testid.includes("characteristic") ||
                    testid.includes("parameter") ||
                    testid.includes("option")
                ) {

                    const text = clean(
                        el.innerText || el.textContent
                    );

                    const match = text.match(
                        /^([^:]{1,100}):\\s*(.+)$/
                    );

                    if (match) {
                        addSpec(
                            match[1],
                            match[2]
                        );
                    }
                }
            });

            // -----------------------------------------------
            // RAW TEXT
            // -----------------------------------------------

            const rawText = clean(
                document.body
                    ? document.body.innerText
                    : ""
            );

            return {
                title,
                description,
                specs,
                raw_text: rawText
            };
        }
        """)

        if not isinstance(result, dict):
            result = {}

        print(
            "[WB PARSER] DOM FALLBACK: "
            f"title={bool(result.get('title'))} "
            f"description={len(result.get('description', '') or '')} "
            f"specs={len(result.get('specs', {}) or {})}"
        )

        return result

    def _parse_dom_specs(self, page) -> dict:

        specs = {}

        selectors = [
            "[class*='characteristic'] li",
            "[class*='characteristics'] li",
            "[class*='option'] li",
            "[class*='options'] li",
            "[class*='param'] li",
            "[class*='params'] li",
            "[class*='spec'] li",
            "dl",
        ]

        for selector in selectors:

            try:

                rows = page.locator(selector)
                count = rows.count()

                if not count:
                    continue

                for i in range(count):

                    row = rows.nth(i)

                    # ------------------------------
                    # dl / dt / dd
                    # ------------------------------

                    dts = row.locator("dt")
                    dds = row.locator("dd")

                    if dts.count() and dds.count():

                        for j in range(
                            min(
                                dts.count(),
                                dds.count(),
                            )
                        ):

                            key = (
                                dts.nth(j)
                                .inner_text()
                                .strip()
                                .rstrip(":")
                            )

                            value = (
                                dds.nth(j)
                                .inner_text()
                                .strip()
                            )

                            if key and value:
                                specs[key] = value

                        continue

                    # ------------------------------
                    # обычный row
                    # ------------------------------

                    spans = row.locator("span")

                    if spans.count() >= 2:

                        key = (
                            spans.nth(0)
                            .inner_text()
                            .strip()
                            .rstrip(":")
                        )

                        value = (
                            spans.nth(1)
                            .inner_text()
                            .strip()
                        )

                        if key and value:
                            specs[key] = value

                if specs:
                    return specs

            except Exception:
                continue

        return specs

    # ==========================================================
    # TEXT
    # ==========================================================

    def _text(
        self,
        page,
        selectors,
    ) -> str:

        for selector in selectors:

            try:

                locator = page.locator(
                    selector
                ).first

                value = locator.inner_text(
                    timeout=1000
                )

                if value:
                    return value.strip()

            except Exception:
                continue

        return ""

    # ==========================================================
    # DEBUG
    # ==========================================================

    @staticmethod
    def _print_result(result):

        print()
        print("[WB PARSER] RESULT")

        print(
            f"TITLE: {result.get('title', '')}"
        )

        print(
            "DESCRIPTION LENGTH: "
            f"{len(result.get('description', '') or '')}"
        )

        print(
            "SPECS: "
            f"{len(result.get('specs', {}) or {})}"
        )
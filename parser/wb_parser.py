import json
import re


class WBParser:

    def parse_page(self, page):

        print("[WB PARSER] Начинаем разбор страницы")

        data = self._extract_page_data(page)

        title = ""
        description = ""
        specs = {}

        # ==========================================================
        # 1. JSON / STATE
        # ==========================================================

        if data:
            product = self._find_product(data)

            if product:
                print("[WB PARSER] Product найден")

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

                specs = self._extract_specs(product)

        # ==========================================================
        # 2. DOM FALLBACK
        # ==========================================================

        if not title:
            title = self._text(
                page,
                [
                    "h1",
                    "[class*=product-page] h1",
                    "[class*=product] h1",
                    "[data-testid*=product] h1",
                ],
            )

        if not description:
            description = self._text(
                page,
                [
                    "[class*=description]",
                    "[class*=about]",
                    "[data-testid*=description]",
                ],
            )

        if not specs:
            specs = self._parse_dom_specs(page)

        # ==========================================================
        # 3. RAW TEXT
        # ==========================================================

        try:
            raw_text = page.locator("body").inner_text(timeout=5000)
        except Exception:
            raw_text = ""

        print(
            f"[WB PARSER] TITLE: {title[:150] if title else '-'}"
        )
        print(
            f"[WB PARSER] DESCRIPTION: "
            f"{len(description)} chars"
        )
        print(
            f"[WB PARSER] SPECS: {len(specs)}"
        )

        return {
            "title": str(title).strip(),
            "description": str(description).strip(),
            "specs": specs,
            "raw_text": raw_text,
            "sections": {},
            "parser_log": [],
        }

    # ==============================================================
    # PAGE DATA
    # ==============================================================

    def _extract_page_data(self, page):

        # ----------------------------------------------------------
        # Сначала ищем JSON в DOM.
        # Это намного надёжнее, чем requests.get() второго URL.
        # ----------------------------------------------------------

        try:
            scripts = page.locator(
                'script[type="application/ld+json"]'
            )

            count = scripts.count()

            for i in range(count):

                try:
                    text = scripts.nth(i).inner_text()

                    if not text:
                        continue

                    data = json.loads(text)

                    if data:
                        return data

                except Exception:
                    continue

        except Exception:
            pass

        # ----------------------------------------------------------
        # Затем ищем JSON/state прямо в HTML.
        # ----------------------------------------------------------

        try:
            html = page.content()

            data = self._extract_json_from_html(html)

            if data:
                return data

        except Exception:
            pass

        # ----------------------------------------------------------
        # Ищем WB card.json среди уже загруженных resource.
        # НИКАКИХ requests.get().
        # ----------------------------------------------------------

        try:

            urls = page.evaluate(
                """
                () => performance
                    .getEntriesByType("resource")
                    .map(r => r.name)
                """
            )

            for url in urls:

                if "card.json" not in url.lower():
                    continue

                print(
                    "[WB PARSER] Найден card.json:",
                    url
                )

                # Иногда сам JSON можно получить через fetch
                # из контекста страницы, где уже есть cookies.
                try:

                    result = page.evaluate(
                        """
                        async (url) => {
                            try {
                                const response = await fetch(url, {
                                    credentials: "include"
                                });

                                if (!response.ok) {
                                    return null;
                                }

                                return await response.json();
                            } catch (e) {
                                return null;
                            }
                        }
                        """,
                        url,
                    )

                    if result:
                        return result

                except Exception:
                    continue

        except Exception as e:

            print(
                "[WB PARSER] Ошибка поиска resource:",
                repr(e)
            )

        return None

    # ==============================================================
    # JSON FROM HTML
    # ==============================================================

    def _extract_json_from_html(self, html):

        if not html:
            return None

        # ----------------------------------------------------------
        # __NEXT_DATA__
        # ----------------------------------------------------------

        match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>'
            r'(.*?)'
            r'</script>',
            html,
            re.IGNORECASE | re.DOTALL,
        )

        if match:

            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # ----------------------------------------------------------
        # JSON-LD
        # ----------------------------------------------------------

        matches = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>'
            r'(.*?)'
            r'</script>',
            html,
            re.IGNORECASE | re.DOTALL,
        )

        for text in matches:

            try:
                data = json.loads(text)

                if data:
                    return data

            except Exception:
                continue

        return None

    # ==============================================================
    # FIND PRODUCT
    # ==============================================================

    def _find_product(self, obj):

        if isinstance(obj, dict):

            # ------------------------------------------------------
            # Текущий вариант
            # ------------------------------------------------------

            if (
                "imt_name" in obj
                and (
                    "description" in obj
                    or "options" in obj
                    or "characteristics" in obj
                    or "params" in obj
                )
            ):
                return obj

            # ------------------------------------------------------
            # Другие возможные варианты WB
            # ------------------------------------------------------

            if (
                (
                    "name" in obj
                    or "title" in obj
                    or "goodsName" in obj
                )
                and (
                    "options" in obj
                    or "characteristics" in obj
                    or "params" in obj
                    or "description" in obj
                )
            ):
                return obj

            for value in obj.values():

                result = self._find_product(value)

                if result:
                    return result

        elif isinstance(obj, list):

            for item in obj:

                result = self._find_product(item)

                if result:
                    return result

        return None

    # ==============================================================
    # SPECS
    # ==============================================================

    def _extract_specs(self, product):

        specs = {}

        options = (
            product.get("options")
            or product.get("characteristics")
            or product.get("params")
            or product.get("props")
            or []
        )

        if isinstance(options, dict):

            for key, value in options.items():

                if value is None:
                    continue

                if isinstance(value, (list, dict)):
                    value = self._stringify_value(value)

                if str(key).strip() and str(value).strip():

                    specs[str(key).strip()] = str(
                        value
                    ).strip()

        elif isinstance(options, list):

            for item in options:

                if not isinstance(item, dict):
                    continue

                key = (
                    item.get("name")
                    or item.get("title")
                    or item.get("key")
                    or item.get("label")
                )

                value = (
                    item.get("value")
                    or item.get("text")
                    or item.get("description")
                    or item.get("values")
                )

                if value is None:
                    continue

                if isinstance(value, (list, dict)):
                    value = self._stringify_value(value)

                if key and str(value).strip():

                    specs[str(key).strip()] = str(
                        value
                    ).strip()

        return specs

    def _stringify_value(self, value):

        if isinstance(value, list):

            result = []

            for item in value:

                if isinstance(item, dict):

                    result.append(
                        str(
                            item.get("name")
                            or item.get("value")
                            or item.get("text")
                            or ""
                        )
                    )

                else:
                    result.append(str(item))

            return ", ".join(
                x for x in result if x
            )

        if isinstance(value, dict):

            for key in (
                "name",
                "value",
                "text",
                "title",
            ):

                if key in value and value[key]:

                    return str(value[key])

            return ", ".join(
                f"{k}: {v}"
                for k, v in value.items()
            )

        return str(value)

    # ==============================================================
    # DOM SPECS
    # ==============================================================

    def _parse_dom_specs(self, page):

        specs = {}

        selectors = [
            "[class*=characteristics] li",
            "[class*=characteristic] li",
            "[class*=options] li",
            "[class*=params] li",
            "[class*=spec] li",
            "[data-testid*=characteristic] li",
            "dl",
        ]

        for selector in selectors:

            try:

                rows = page.locator(selector)

                count = rows.count()

                if not count:
                    continue

                if selector == "dl":

                    for i in range(count):

                        dl = rows.nth(i)

                        dts = dl.locator("dt")
                        dds = dl.locator("dd")

                        pairs = min(
                            dts.count(),
                            dds.count(),
                        )

                        for j in range(pairs):

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

                else:

                    for i in range(count):

                        row = rows.nth(i)

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

    # ==============================================================
    # TEXT
    # ==============================================================

    def _text(self, page, selectors):

        for selector in selectors:

            try:

                locator = page.locator(selector).first

                value = locator.inner_text(
                    timeout=1000
                )

                if value:
                    return value.strip()

            except Exception:
                continue

        return ""
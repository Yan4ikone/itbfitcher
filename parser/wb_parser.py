import requests


class WBParser:

    def parse_page(self, page):

        data = self._extract_json(page)
        title = ""
        description = ""
        specs = {}

        if data:

            product = self._find_product(data)
            print(product)

            if product:

                title = (
                    product.get("imt_name")
                    or product.get("name")
                    or product.get("title")
                    or ""
                )
                description = (
                    product.get("description")
                    or product.get("descriptionText")
                    or ""
                )
                options = (
                    product.get("options")
                    or product.get("characteristics")
                    or product.get("params")
                    or []
                )
                if isinstance(options, list):

                    for item in options:

                        key = (
                            item.get("name")
                            or item.get("title")
                            or item.get("key")
                        )
                        value = (
                            item.get("value")
                            or item.get("text")
                            or item.get("description")
                        )
                        if key and value:
                            specs[str(key)] = str(value)

                elif isinstance(options, dict):
                    specs.update(options)

        if not title:
            title = self._text(page, [
                "h1",
                "[class*=product-page] h1",
                "[class*=product] h1",
            ])
        if not description:
            description = self._text(page, [
                "[class*=description]",
                "[class*=about]",
            ])
        if not specs:
            specs = self._parse_dom_specs(page)
        raw_text = page.locator("body").inner_text()

        return {
            "title": title,
            "description": description,
            "specs": specs,
            "raw_text": raw_text,
            "sections": {},
            "parser_log": [],
        }

    # ---------------------------------------------------------

    def _extract_json(self, page):

        for _ in range(40):

            urls = page.evaluate("""
            () => performance.getEntriesByType("resource")
                .map(r => r.name)
            """)

            for url in urls:

                if "/card.json" in url:
                    try:
                        return requests.get(
                            url,
                            timeout=10,
                            headers={
                                "User-Agent": "Mozilla/5.0"
                            }
                        ).json()

                    except Exception:
                        return None

            page.wait_for_timeout(250)

        return None

    # ---------------------------------------------------------

    def _find_product(self, obj):

        if isinstance(obj, dict):

            if (
                    "imt_name" in obj
                    and (
                    "description" in obj
                    or "options" in obj
                    or "characteristics" in obj
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

    # ---------------------------------------------------------

    def _parse_dom_specs(self, page):

        specs = {}
        selectors = [
            "[class*=characteristics] li",
            "[class*=options] li",
            "[class*=params] li",
            "[class*=spec] li",
            "dl",
        ]
        for selector in selectors:

            try:

                rows = page.locator(selector)

                if not rows.count():
                    continue

                if selector == "dl":

                    for i in range(rows.count()):

                        dl = rows.nth(i)

                        dts = dl.locator("dt")
                        dds = dl.locator("dd")

                        for j in range(min(dts.count(), dds.count())):

                            key = dts.nth(j).inner_text().strip().rstrip(":")
                            value = dds.nth(j).inner_text().strip()

                            if key and value:
                                specs[key] = value

                else:

                    for i in range(rows.count()):
                        row = rows.nth(i)
                        spans = row.locator("span")
                        if spans.count() >= 2:
                            key = spans.nth(0).inner_text().strip().rstrip(":")
                            value = spans.nth(1).inner_text().strip()
                            if key and value:
                                specs[key] = value
                if specs:
                    return specs
            except:
                pass
        return specs

    # ---------------------------------------------------------

    def _text(self, page, selectors):

        for selector in selectors:
            try:
                value = page.locator(selector).first.inner_text(timeout=1000)
                if value:
                    return value.strip()
            except:
                pass
        return ""
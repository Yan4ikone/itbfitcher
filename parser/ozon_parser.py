import re
from urllib.parse import urlparse, unquote

from utils.material_extractor import extract_material as _shared_extract_material

IMPORTANT_FIELDS = [
    "Тип",
    "Тип товара",
    "Вид товара",
    "Материал",
    "Назначение",
    "Назначение емкости для хранения",
    "Особенности",
    "Комплектация",
    "Форма",
    "Конструкция",
    "Количество в упаковке, шт",
    "Страна-изготовитель",
    "Бренд",
]
SECTION_HEADERS = {
    "Описание": "description",
    "Характеристики": "specs",
    "Отзывы": "reviews",
    "Вопросы": "questions",
    "Похожие товары": "similar",
    "С этим товаром покупают": "similar",
    "Рекомендуем также": "similar",
    "Вам может понравиться": "similar",
    "Другие предложения": "similar",
}


class OzonParser:

    def __init__(self):
        pass

    # ==========================================================
    # SAFE HELPERS
    # ==========================================================

    def safe_text(self, locator):

        try:
            if locator.count():
                return locator.first.inner_text().strip()
        except Exception as e:
            print(f"[OZON SAFE TEXT ERROR] {e}")

        return ""

    def normalize_text(self, text):

        if not text:
            return ""

        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    # ==========================================================
    # IMAGES
    # ==========================================================

    def extract_images(self, page):

        images = []

        try:

            img_locators = page.locator("img").all()

            print(
                f"[OZON IMAGES] Found img elements: "
                f"{len(img_locators)}"
            )

            for img in img_locators:

                try:

                    src = (
                        img.get_attribute("src")
                        or img.get_attribute("data-src")
                        or img.get_attribute("data-original")
                    )

                    if not src:
                        continue

                    src_lower = src.lower()

                    if "logo" in src_lower:
                        continue

                    if (
                        "ozone.ru" not in src_lower
                        and
                        "ozonusercontent.com" not in src_lower
                    ):
                        continue

                    if "/wc50/" in src:
                        src = src.replace(
                            "/wc50/",
                            "/wc1000/"
                        )

                    elif "/wc100/" in src:
                        src = src.replace(
                            "/wc100/",
                            "/wc1000/"
                        )

                    images.append(src)

                except Exception as e:

                    print(
                        f"[OZON IMAGE ITEM ERROR] {e}"
                    )

        except Exception as e:

            print(
                f"[OZON IMAGE EXTRACT ERROR] {e}"
            )

        images = list(dict.fromkeys(images))

        print(
            f"[OZON IMAGES] Extracted: "
            f"{len(images)}"
        )

        if not images:

            print(
                "[OZON WARNING] "
                "No product images found"
            )

        return images

    # ==========================================================
    # FULL PAGE TEXT
    # ==========================================================

    def get_full_page_text(self, page):

        try:

            text = page.locator("body").inner_text()

            text = self.normalize_text(text)

            print(
                f"[OZON PAGE TEXT] "
                f"{len(text)} chars"
            )

            return text

        except Exception as e:

            print(
                f"[OZON PAGE TEXT ERROR] {e}"
            )

            return ""

    # ==========================================================
    # TITLE
    # ==========================================================

    def extract_title_dom(self, page, parser_log):

        selectors = [
            "h1",
            '[data-widget="webProductHeading"] h1',
            '[data-widget="webProductHeading"]',
        ]

        for selector in selectors:

            try:

                title = self.safe_text(
                    page.locator(selector)
                )

                if title:

                    parser_log.append(
                        f"TITLE <- {selector}"
                    )

                    print(
                        f"[OZON TITLE] "
                        f"Selector: {selector}"
                    )

                    print(
                        f"[OZON TITLE] "
                        f"{title}"
                    )

                    return title

            except Exception as e:

                parser_log.append(
                    f"TITLE ERROR <- "
                    f"{selector}: {e}"
                )

        return ""

    # ==========================================================
    # DESCRIPTION
    # ==========================================================

    def extract_description_dom(
        self,
        page,
        parser_log,
    ):

        selectors = [

            '[data-widget="webDescription"]',

            '[data-widget="webProductDescription"]',

            '[data-widget*="Description"]',

            '[id="section-description"]',

            'section[id*="description"]',

        ]

        for selector in selectors:

            try:

                locator = page.locator(selector)

                count = locator.count()

                if not count:
                    continue

                texts = []

                for i in range(
                    min(count, 10)
                ):

                    try:

                        text = (
                            locator.nth(i)
                            .inner_text()
                            .strip()
                        )

                        if text:
                            texts.append(text)

                    except Exception:
                        continue

                candidate = "\n".join(texts)

                candidate = self.normalize_text(
                    candidate
                )

                if len(candidate) >= 20:

                    parser_log.append(
                        f"DESCRIPTION <- {selector}"
                    )

                    print(
                        f"[OZON DESCRIPTION] "
                        f"Selector: {selector}"
                    )

                    print(
                        f"[OZON DESCRIPTION] "
                        f"Length: {len(candidate)}"
                    )

                    return candidate

            except Exception as e:

                parser_log.append(
                    f"DESCRIPTION ERROR <- "
                    f"{selector}: {e}"
                )

        return ""

    # ==========================================================
    # DESCRIPTION FROM FULL PAGE
    # ==========================================================

    def extract_description_from_text(
        self,
        page_text,
        parser_log,
    ):

        if not page_text:
            return ""

        lines = [
            line.strip()
            for line in page_text.splitlines()
            if line.strip()
        ]

        if not lines:
            return ""

        start_index = None

        for i, line in enumerate(lines):

            if line.lower() == "описание":

                start_index = i + 1
                break

        if start_index is None:

            print(
                "[OZON DESCRIPTION TEXT] "
                "Section 'Описание' not found"
            )

            return ""

        result = []

        stop_headers = {
            "характеристики",
            "отзывы",
            "вопросы",
            "похожие товары",
            "с этим товаром покупают",
            "рекомендуем также",
            "вам может понравиться",
            "другие предложения",
        }

        for line in lines[start_index:]:

            if line.lower() in stop_headers:
                break

            result.append(line)

        description = self.normalize_text(
            "\n".join(result)
        )

        if description:

            parser_log.append(
                "DESCRIPTION <- full page text"
            )

            print(
                "[OZON DESCRIPTION] "
                "Recovered from full page text"
            )

            print(
                f"[OZON DESCRIPTION] "
                f"Length: {len(description)}"
            )

        return description

    # ==========================================================
    # SPECS FROM DL/DT/DD
    # ==========================================================

    def extract_specs_dl(self, page, parser_log):

        specs = {}

        try:

            rows = page.locator("dl dt").all()

            print(
                f"[OZON SPECS] "
                f"dt elements found: {len(rows)}"
            )

            for dt in rows:

                try:

                    key = (
                        dt.inner_text()
                        .strip()
                    )

                    if not key:
                        continue

                    dd = dt.locator(
                        "xpath=following-sibling::dd[1]"
                    )

                    if not dd.count():
                        continue

                    value = (
                        dd.inner_text()
                        .strip()
                    )

                    if not value:
                        continue

                    specs[key] = value

                except Exception as e:

                    print(
                        f"[OZON SPEC ITEM ERROR] "
                        f"{e}"
                    )

            print(
                f"[OZON SPECS] "
                f"Extracted via dl: "
                f"{len(specs)}"
            )

        except Exception as e:

            parser_log.append(
                f"SPECS DL ERROR: {e}"
            )

            print(
                f"[OZON SPECS ERROR] "
                f"{e}"
            )

        return specs

    # ==========================================================
    # SPECS FROM FULL PAGE TEXT
    # ==========================================================

    def extract_specs_from_text(
        self,
        page_text,
        parser_log,
    ):

        specs = {}

        if not page_text:
            return specs

        lines = [
            line.strip()
            for line in page_text.splitlines()
            if line.strip()
        ]

        if not lines:
            return specs

        start_index = None

        for i, line in enumerate(lines):

            if line.lower() == "характеристики":

                start_index = i + 1
                break

        if start_index is None:

            print(
                "[OZON SPECS TEXT] "
                "Section 'Характеристики' not found"
            )

            return specs

        stop_headers = {
            "описание",
            "отзывы",
            "вопросы",
            "похожие товары",
            "с этим товаром покупают",
            "рекомендуем также",
            "вам может понравиться",
            "другие предложения",
        }

        section = []

        for line in lines[start_index:]:

            if line.lower() in stop_headers:
                break

            section.append(line)

        # ------------------------------------------------------
        # Ищем пары KEY -> VALUE
        # ------------------------------------------------------

        for i in range(len(section) - 1):

            key = section[i].strip()
            value = section[i + 1].strip()

            if not key or not value:
                continue

            if key in IMPORTANT_FIELDS:

                specs[key] = value

        if specs:

            parser_log.append(
                f"SPECS <- full page text: "
                f"{len(specs)}"
            )

            print(
                "[OZON SPECS TEXT] "
                f"Recovered: {len(specs)}"
            )

        return specs

    # ==========================================================
    # GENERAL TEXT EXTRACTION
    # ==========================================================

    def split_sections(self, page_text):

        lines = [
            x.strip()
            for x in page_text.splitlines()
            if x.strip()
        ]

        parser_log = []

        parser_log.append(
            f"Всего строк: {len(lines)}"
        )

        sections = {
            "title": [],
            "description": [],
            "specs": [],
            "reviews": [],
            "questions": [],
            "similar": [],
            "other": [],
        }

        current = "title"

        for line in lines:

            if line in SECTION_HEADERS:

                current = SECTION_HEADERS[line]

                parser_log.append(
                    f"Секция -> {current}"
                )

                continue

            sections[current].append(line)

        return sections, parser_log

    def extract_specs(self, section):

        specs = {}

        lines = section

        for i in range(len(lines) - 1):

            key = lines[i].strip()
            value = lines[i + 1].strip()

            if key in IMPORTANT_FIELDS:

                specs[key] = value

        return specs

    def extract_title(self, section):

        for line in section:

            if len(line) < 5:
                continue

            if "артикул" in line.lower():
                continue

            return line

        return ""

    def extract_description(self, section):

        text = []

        for line in section:

            if len(line) < 2:
                continue

            text.append(line)

        return " ".join(text)

    # ==========================================================
    # MATERIAL
    # ==========================================================

    def _extract_material(self, text):
        # Делегирует в единый источник (utils/material_extractor.py),
        # который проверяет найденное по метке значение против словаря
        # известных материалов (MATERIAL_ALIASES) и не возвращает
        # неподтверждённую сырую строку вроде "сплав цанги"/"мягкого".
        # Раньше здесь был независимый дубль тех же паттернов без
        # какой-либо проверки - это и было источником мусорных значений.
        return _shared_extract_material(text)

    # ==========================================================
    # QUANTITY
    # ==========================================================

    def _extract_quantity(self, text):

        if not text:
            return ""

        patterns = [

            (
                r"количество.*?(\d+)\s*шт",
                "шт",
            ),

            (
                r"(\d+)\s*шт",
                "шт",
            ),

            (
                r"(\d+)\s*пары",
                "пары",
            ),

            (
                r"(\d+)\s*комплект",
                "комплект",
            ),

            (
                r"комплект\s+из\s+(\d+)",
                "комплект",
            ),
        ]

        for pattern, suffix in patterns:

            match = re.search(
                pattern,
                text,
                re.I,
            )

            if match:

                return (
                    f"{match.group(1)} "
                    f"{suffix}"
                )

        return ""

    # ==========================================================
    # REPAIR
    # ==========================================================

    def repair_deleted_card(
        self,
        page,
        parsed,
        url,
    ):

        parser_log = parsed.setdefault(
            "parser_log",
            [],
        )

        # ------------------------------------------------------
        # TITLE
        # ------------------------------------------------------

        if not parsed.get("title"):

            try:

                h1 = (
                    page.locator("h1")
                    .first
                    .inner_text()
                    .strip()
                )

                if h1:

                    parsed["title"] = h1

                    parser_log.append(
                        "TITLE REPAIR <- h1"
                    )

                    print(
                        "[OZON REPAIR] "
                        "Title recovered from h1"
                    )

            except Exception as e:

                parser_log.append(
                    f"TITLE REPAIR h1 ERROR: {e}"
                )

        if not parsed.get("title"):

            try:

                title = page.locator(
                    'meta[property="og:title"]'
                ).get_attribute(
                    "content"
                )

                if title:

                    parsed["title"] = (
                        title.strip()
                    )

                    parser_log.append(
                        "TITLE REPAIR <- og:title"
                    )

                    print(
                        "[OZON REPAIR] "
                        "Title recovered from og:title"
                    )

            except Exception as e:

                parser_log.append(
                    f"TITLE REPAIR og ERROR: {e}"
                )

        if not parsed.get("title"):

            try:

                title = page.title()

                if title:

                    title = title.replace(
                        "OZON",
                        "",
                    )

                    title = title.replace(
                        "|",
                        "",
                    )

                    title = title.strip()

                    if title:

                        parsed["title"] = title

                        parser_log.append(
                            "TITLE REPAIR <- page.title"
                        )

            except Exception as e:

                parser_log.append(
                    f"TITLE REPAIR page.title ERROR: {e}"
                )

        if not parsed.get("title"):

            try:

                path = unquote(
                    urlparse(url).path
                )

                m = re.search(
                    r"/product/(.+?)-\d+/?$",
                    path,
                )

                if m:

                    slug = (
                        m.group(1)
                        .replace("-", " ")
                        .strip()
                    )

                    if slug:

                        parsed["title"] = slug

                        parser_log.append(
                            "TITLE REPAIR <- URL slug"
                        )

            except Exception as e:

                parser_log.append(
                    f"TITLE REPAIR URL ERROR: {e}"
                )

        # ------------------------------------------------------
        # DESCRIPTION
        # ------------------------------------------------------

        if (
            not parsed.get("description")
            or
            parsed["description"] == "Распродажа"
        ):

            if parsed.get("title"):

                parsed["description"] = (
                    parsed["title"]
                )

                parser_log.append(
                    "DESCRIPTION REPAIR <- title"
                )

                print(
                    "[OZON REPAIR] "
                    "Description recovered from title"
                )

        # ------------------------------------------------------
        # SLUG
        # ------------------------------------------------------

        if (
            not parsed.get("slug")
            and
            parsed.get("title")
        ):

            parsed["slug"] = parsed["title"]

            parser_log.append(
                "SLUG REPAIR <- title"
            )

        # ------------------------------------------------------
        # CLEANED TEXT
        # ------------------------------------------------------

        if (
            not parsed.get("cleaned_text")
            and
            parsed.get("title")
        ):

            parsed["cleaned_text"] = (
                parsed["title"]
            )

            parser_log.append(
                "CLEANED TEXT REPAIR <- title"
            )

        return parsed

    # ==========================================================
    # MAIN PARSER
    # ==========================================================

    def _fetch_features_page_specs(self, page, parser_log):
        """
        Основная страница товара Ozon показывает только часть
        характеристик - полная таблица лежит на отдельной странице
        .../features/. Заходим туда ДОПОЛНИТЕЛЬНО, после того как
        title/description/specs с основной страницы уже собраны,
        и возвращаемся обратно - чтобы последующий код (например,
        извлечение изображений) продолжал работать с исходной
        страницей товара.
        Намеренно не бросает исключения наружу - это дополнительный,
        не обязательный источник: если переход не удался (таймаут,
        антибот-блокировка, изменившаяся структура сайта), парсинг
        должен продолжиться с тем, что уже есть с основной страницы,
        а не падать целиком.
        """

        specs = {}

        try:

            current_url = page.url

            if not current_url or "/features" in current_url:
                return specs

            features_url = current_url.rstrip("/") + "/features/"

            parser_log.append(
                f"FEATURES PAGE: {features_url}"
            )

            print(
                f"[OZON FEATURES PAGE] Переход: {features_url}"
            )

            page.goto(
                features_url,
                timeout=15000,
                wait_until="domcontentloaded",
            )

            page.wait_for_timeout(1000)

            specs = self.extract_specs_dl(
                page,
                parser_log,
            )

            print(
                f"[OZON FEATURES PAGE] "
                f"Извлечено характеристик: {len(specs)}"
            )

            page.goto(
                current_url,
                timeout=15000,
                wait_until="domcontentloaded",
            )

        except Exception as e:

            print(
                f"[OZON FEATURES PAGE ERROR] {e}"
            )

            parser_log.append(
                f"FEATURES PAGE ERROR: {e}"
            )

        return specs

    def parse_page(self, page):

        parser_log = []

        parsed = {
            "title": "",
            "description": "",
            "specs": {},
            "images": [],
            "raw_text": "",
            "parser_log": parser_log,
        }

        print(
            "\n========== OZON PARSER =========="
        )

        try:

            print(
                f"[OZON URL] {page.url}"
            )

            parser_log.append(
                f"URL: {page.url}"
            )

        except Exception as e:

            print(
                f"[OZON PAGE INFO ERROR] {e}"
            )

            parser_log.append(
                f"PAGE INFO ERROR: {e}"
            )

        # ======================================================
        # FULL PAGE TEXT
        # ======================================================

        page_text = self.get_full_page_text(
            page
        )

        parsed["page_text"] = page_text

        # ======================================================
        # TITLE
        # ======================================================

        title = self.extract_title_dom(
            page,
            parser_log,
        )

        if not title and page_text:

            sections, text_log = (
                self.split_sections(page_text)
            )

            parser_log.extend(text_log)

            title = self.extract_title(
                sections["title"]
            )

            if title:

                parser_log.append(
                    "TITLE <- full page text"
                )

                print(
                    "[OZON TITLE] "
                    "Recovered from full page text"
                )

        parsed["title"] = title

        if not title:

            parser_log.append(
                "TITLE NOT FOUND"
            )

            print(
                "[OZON WARNING] "
                "TITLE NOT FOUND"
            )

        # ======================================================
        # DESCRIPTION
        # ======================================================

        description = (
            self.extract_description_dom(
                page,
                parser_log,
            )
        )

        if not description:

            description = (
                self.extract_description_from_text(
                    page_text,
                    parser_log,
                )
            )

        parsed["description"] = description

        if not description:

            parser_log.append(
                "DESCRIPTION NOT FOUND"
            )

            print(
                "[OZON WARNING] "
                "DESCRIPTION NOT FOUND"
            )

        # ======================================================
        # SPECS
        # ======================================================

        specs = self.extract_specs_dl(
            page,
            parser_log,
        )

        text_specs = (
            self.extract_specs_from_text(
                page_text,
                parser_log,
            )
        )

        # DOM wins if the same field exists.
        for key, value in text_specs.items():

            if key not in specs:
                specs[key] = value

        # ======================================================
        # ПОЛНАЯ СТРАНИЦА ХАРАКТЕРИСТИК (.../features/)
        #
        # Основная страница товара показывает только ЧАСТЬ
        # характеристик - полная таблица лежит на отдельной
        # странице .../features/
        # Дополнительный источник: если поле уже есть с основной
        # страницы - не перезаписываем (DOM основной страницы
        # приоритетнее, features - это добор недостающего).
        # ======================================================

        features_specs = self._fetch_features_page_specs(
            page,
            parser_log,
        )

        for key, value in features_specs.items():

            if key not in specs:
                specs[key] = value

        parsed["specs"] = specs

        if not specs:

            parser_log.append(
                "SPECS NOT FOUND"
            )

            print(
                "[OZON WARNING] "
                "No specs found"
            )

        # ======================================================
        # MATERIAL
        # ======================================================

        if "Материал" not in parsed["specs"]:

            material = (
                self._extract_material(
                    parsed["description"]
                )
            )

            if material:

                parsed["specs"]["Материал"] = (
                    material
                )

                parser_log.append(
                    f"MATERIAL FROM DESCRIPTION: "
                    f"{material}"
                )

                print(
                    "[OZON MATERIAL] "
                    f"{material}"
                )

        # ======================================================
        # QUANTITY
        # ======================================================

        if (
            "Количество" not in parsed["specs"]
            and
            "Количество в упаковке, шт"
            not in parsed["specs"]
        ):

            quantity = (
                self._extract_quantity(
                    parsed["description"]
                )
            )

            if quantity:

                parsed["specs"]["Количество"] = (
                    quantity
                )

                parser_log.append(
                    f"QUANTITY FROM DESCRIPTION: "
                    f"{quantity}"
                )

                print(
                    "[OZON QUANTITY] "
                    f"{quantity}"
                )

        # ======================================================
        # REPAIR
        # ======================================================

        parsed = self.repair_deleted_card(
            page,
            parsed,
            page.url,
        )

        # ======================================================
        # SECONDARY MATERIAL / QUANTITY
        # ======================================================

        if "Материал" not in parsed["specs"]:

            material = (
                self._extract_material(
                    parsed.get(
                        "raw_text",
                        "",
                    )
                )
            )

            if material:

                parsed["specs"]["Материал"] = (
                    material
                )

        if (
            "Количество" not in parsed["specs"]
            and
            "Количество в упаковке, шт"
            not in parsed["specs"]
        ):

            quantity = (
                self._extract_quantity(
                    parsed.get(
                        "description",
                        "",
                    )
                )
            )

            if quantity:

                parsed["specs"]["Количество"] = (
                    quantity
                )

        # ======================================================
        # RAW TEXT
        # ======================================================

        parts = []

        if parsed.get("title"):
            parts.append(
                parsed["title"]
            )

        if parsed.get("description"):
            parts.append(
                parsed["description"]
            )

        for key, value in parsed.get(
            "specs",
            {},
        ).items():

            if key and value:

                parts.append(
                    f"{key}: {value}"
                )

        parsed["raw_text"] = (
            "\n".join(parts)
        )

        parser_log.append(
            f"RAW TEXT: "
            f"{len(parsed['raw_text'])} chars"
        )

        # ======================================================
        # IMAGES
        # ======================================================

        parsed["images"] = (
            self.extract_images(page)
        )

        parser_log.append(
            f"IMAGES: "
            f"{len(parsed['images'])}"
        )

        # ======================================================
        # FINAL
        # ======================================================

        print(
            "\n========== OZON PARSER RESULT =========="
        )

        print(
            f"[OZON RESULT] TITLE: "
            f"{bool(parsed.get('title'))}"
        )

        print(
            f"[OZON RESULT] DESCRIPTION: "
            f"{len(parsed.get('description', ''))} chars"
        )

        print(
            f"[OZON RESULT] SPECS: "
            f"{len(parsed.get('specs', {}))}"
        )

        print(
            f"[OZON RESULT] IMAGES: "
            f"{len(parsed.get('images', []))}"
        )

        print(
            f"[OZON RESULT] RAW TEXT: "
            f"{len(parsed.get('raw_text', ''))} chars"
        )

        print(
            "========================================\n"
        )

        return parsed
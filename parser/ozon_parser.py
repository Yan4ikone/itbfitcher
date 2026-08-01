import re
from urllib.parse import urlparse, unquote

from models.card_builder import extract_slug

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
    "Бренд"
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

    def safe_text(self, locator):

        try:

            if locator.count():

                return locator.first.inner_text().strip()

        except Exception:
            pass

        return ""

    def parse_page(self, page):

        parser_log = []
        parsed = {
            "title": "",
            "description": "",
            "specs": {},
            "raw_text": "",
            "parser_log": parser_log
        }

        for selector in [
            "h1",
            '[data-widget="webProductHeading"] h1',
            '[data-widget="webProductHeading"]',
        ]:

            title = self.safe_text(page.locator(selector))

            if title:
                parser_log.append(
                    f"TITLE <- {selector}"
                )
                break

        parsed["title"] = title

        for selector in [
            '[data-widget="webDescription"]',
            '[data-widget="webProductDescription"]',
            'section'
        ]:

            description = self.safe_text(page.locator(selector))

            if len(description) > 50:

                parser_log.append(f"DESCRIPTION <- {selector}")

                break

        parsed["description"] = description
        specs = {}

        try:

            rows = page.locator("dl dt").all()

            for dt in rows:

                key = dt.inner_text().strip()
                dd = dt.locator("xpath=following-sibling::dd[1]")

                if dd.count():

                    value = dd.inner_text().strip()
                    specs[key] = value

        except Exception:

            pass

        parsed["specs"] = specs
        if "Материал" not in parsed["specs"]:

            material = self._extract_material(parsed["description"])

            if material:
                parsed["specs"]["Материал"] = material

        if (
                "Количество" not in parsed["specs"]
                and "Количество в упаковке, шт" not in parsed["specs"]
        ):

            quantity = self._extract_quantity(parsed["description"])

            if quantity:
                parsed["specs"]["Количество"] = quantity

        parts = []

        if title:
            parts.append(title)

        if description:
            parts.append(description)

        for value in specs.values():

            if value:

                parts.append(str(value))

        parsed["raw_text"] = "\n".join(parts)
        parsed = self.repair_deleted_card(
            page,
            parsed,
            page.url,
        )
        if "Материал" not in parsed["specs"]:
            material = self._extract_material(
                parsed["description"]
            )
            if material:
                parsed["specs"]["Материал"] = material
        if (
                "Количество" not in parsed["specs"]
                and
                "Количество в упаковке, шт"
                not in parsed["specs"]
        ):
            quantity = self._extract_quantity(
                parsed["description"]
            )
            if quantity:
                parsed["specs"]["Количество"] = quantity

        return parsed

    def split_sections(self, page_text):

        lines = [

            x.strip()

            for x in page_text.splitlines()

            if x.strip()

        ]

        parser_log = []
        parser_log.append(f"Всего строк: {len(lines)}")

        sections = {
            "title": [],
            "description": [],
            "specs": [],
            "reviews": [],
            "questions": [],
            "similar": [],
            "other": []
        }

        current = "title"

        for line in lines:

            if line in SECTION_HEADERS:
                current = SECTION_HEADERS[line]
                parser_log.append(f"Секция -> {current}")

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

    def parse_text(self, page_text):

        sections, parser_log = self.split_sections(page_text)
        title = self.extract_title(sections["title"])
        description = self.extract_description(sections["description"])
        specs = self.extract_specs(sections["specs"])
        parser_log.append(f"Название: {title}")
        parser_log.append(f"Описание: {len(description)} символов")
        parser_log.append(f"Характеристик: {len(specs)}")

        return {
            "title": title,
            "description": description,
            "specs": specs,
            "sections": sections,
            "raw_text": page_text,
            "parser_log": parser_log
        }

    def _extract_material(self, description):

        if not description:
            return ""

        patterns = [
            r"материал\s*[:\-]\s*([^\n\r\.]+)",
            r"изготовлен[ао]?\s+из\s+([^\n\r\.]+)",
        ]

        for pattern in patterns:

            m = re.search(pattern, description, re.I)

            if m:
                return m.group(1).strip()

        return ""

    def _extract_quantity(self, description):

        if not description:
            return ""

        patterns = [
            r"количество.*?(\d+)\s*шт",
            r"(\d+)\s*шт",
            r"(\d+)\s*пары",
            r"(\d+)\s*комплект",
            r"комплект\s+из\s+(\d+)",
        ]

        for pattern in patterns:

            m = re.search(pattern, description, re.I)

            if m:

                number = m.group(1)

                if "шт" in pattern:
                    return f"{number} шт"

                if "пары" in pattern:
                    return f"{number} пары"

                return f"{number} комплект"

        return ""

    def _repair_deleted_card(self, parsed, url):

        slug = extract_slug(url)

        if not parsed.get("title"):
            parsed["title"] = slug

        if (
                not parsed.get("description")
                or parsed["description"] == "Распродажа"
        ):
            parsed["description"] = slug

        return parsed


    def repair_deleted_card(self, page, parsed, url):

        if not parsed["title"]:
            try:

                h1 = page.locator("h1").first.inner_text().strip()

                if h1:
                    parsed["title"] = h1

            except Exception:
                pass

        if not parsed["title"]:
            try:

                title = page.locator(
                    'meta[property="og:title"]'
                ).get_attribute("content")

                if title:
                    parsed["title"] = title.strip()

            except Exception:
                pass

        if not parsed["title"]:
            try:

                title = page.title()

                if title:
                    title = title.replace("OZON", "")
                    title = title.replace("|", "")
                    title = title.strip()
                    parsed["title"] = title

            except Exception:
                pass

        if not parsed["title"]:

            path = unquote(urlparse(url).path)

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

                parsed["title"] = slug


        if (
                not parsed["description"]
                or parsed["description"] == "Распродажа"
        ):
            parsed["description"] = parsed["title"]

        if not parsed.get("slug") and parsed.get("title"):
            parsed["slug"] = parsed["title"]
            parsed["description"] = parsed["title"]

        if not parsed.get("cleaned_text"):
            parsed["cleaned_text"] = parsed["title"]

        return parsed
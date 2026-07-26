from playwright.sync_api import TimeoutError

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

        #
        # Название
        #

        title = ""

        for selector in [

            "h1",

            '[data-widget="webProductHeading"] h1',

            '[data-widget="webProductHeading"]',

        ]:

            title = self.safe_text(
                page.locator(selector)
            )

            if title:
                parser_log.append(
                    f"TITLE <- {selector}"
                )
                break

        parsed["title"] = title

        description = ""

        for selector in [

            '[data-widget="webDescription"]',

            '[data-widget="webProductDescription"]',

            'section'

        ]:

            description = self.safe_text(
                page.locator(selector)
            )

            if len(description) > 50:

                parser_log.append(
                    f"DESCRIPTION <- {selector}"
                )

                break

        parsed["description"] = description

        specs = {}

        try:

            rows = page.locator(
                "dl dt"
            ).all()

            for dt in rows:

                key = dt.inner_text().strip()

                dd = dt.locator(
                    "xpath=following-sibling::dd[1]"
                )

                if dd.count():

                    value = dd.inner_text().strip()

                    specs[key] = value

        except Exception:

            pass

        parsed["specs"] = specs

        parts = []

        if title:
            parts.append(title)

        if description:
            parts.append(description)

        for value in specs.values():

            if value:

                parts.append(str(value))

        parsed["raw_text"] = "\n".join(parts)

        return parsed

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
            "other": []

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

    def parse_text(self, page_text):

        sections, parser_log = self.split_sections(page_text)

        title = self.extract_title(
            sections["title"]
        )

        description = self.extract_description(
            sections["description"]
        )

        specs = self.extract_specs(
            sections["specs"]
        )

        parser_log.append(
            f"Название: {title}"
        )

        parser_log.append(
            f"Описание: {len(description)} символов"
        )

        parser_log.append(
            f"Характеристик: {len(specs)}"
        )

        return {

            "title": title,
            "description": description,
            "specs": specs,
            "sections": sections,
            "raw_text": page_text,
            "parser_log": parser_log

        }
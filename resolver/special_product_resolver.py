import re


class SpecialProductResolver:

    BOOK_CODE = "4901990000"

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def resolve(self, card):

        if self._is_book(card):
            return self._resolve_book(card)

        if self._is_air_conditioner(card):
            return self._resolve_air_conditioner()

        return None

    # ==========================================================
    # BOOK
    # ==========================================================

    def _resolve_book(self, card):

        book_title = self._book_title(card)
        publisher = self._publisher(card)

        display_name = (
            f'Книга печатная "{book_title}", '
            f'издательство "{publisher}", '
            f', не содержит запрещенной к ввозу информации'
        )

        return {
            "product": "Книга",
            "display_name": display_name,
            "dropdown": display_name,
            "code": self.BOOK_CODE,
            "source": "SPECIAL_BOOK",
            "confidence": 100,
            "review": False,
        }

    def _structured_text(self, card):

        parts = [
            getattr(card, "title", ""),
        ]

        specs = getattr(card, "specs", {}) or {}

        for key, value in specs.items():

            parts.append(str(key))
            parts.append(str(value))

        return " ".join(
            str(value)
            for value in parts
            if value
        ).lower()

    # ==========================================================
    # AIR CONDITIONER
    # ==========================================================

    def _resolve_air_conditioner(self):

        return {
            "product": "Кондиционер",
            "display_name": "Кондиционер не содержит хладогена",
            "dropdown": "Кондиционер не содержит хладогена",
            "code": "8415109000",
            "source": "SPECIAL_AIR_CONDITIONER",
            "confidence": 100,
            "review": False,
        }

    # ==========================================================
    # DETECTION
    # ==========================================================

    def _is_book(self, card):

        structured = self._structured_text(card)

        strong_keywords = (
            "книга",
            "книгу",
            "книги",
            "учебник",
            "учебное пособие",
            "энциклопедия",
            "печатная книга",
            "печатное издание",
        )

        if structured and any(
                self._contains_phrase(structured, keyword)
                for keyword in strong_keywords
        ):
            return True

        text = self._text(card)

        if not text:
            return False

        literary_keywords = (
            "роман",
            "повесть",
            "рассказ",
            "поэма",
            "стихи",
            "стихотворение",
            "литератур",
        )
        book_context = (
            "автор",
            "автор книги",
            "издатель",
            "издательство",
            "isbn",
            "isbn-",
            "тираж",
            "переплет",
            "обложка",
            "страниц",
            "страница",
            "страниц.",
            "книжн",
            "год издания",
        )
        has_literary = any(
            self._contains_phrase(text, keyword)
            for keyword in literary_keywords
        )
        has_context = any(
            self._contains_phrase(text, keyword)
            for keyword in book_context
        )
        return has_literary and has_context

    def _is_air_conditioner(self, card):

        structured = self._structured_text(card)

        strong_keywords = (
            "сплит-система",
            "сплит система",
            "кондиционер воздуха",
            "кондиционер бытовой",
            "кондиционер настенный",
            "кондиционер напольный",
            "кондиционер оконный",
        )
        if structured and any(
                self._contains_phrase(structured, keyword)
                for keyword in strong_keywords
        ):
            return True

        text = self._text(card)

        if not text:
            return False

        if not self._contains_phrase(text, "кондиционер"):
            return False

        climate_context = (
            "охлаждение", "охлаждать", "охлаждает", "охлаждающий",
            "обогрев", "обогреватель", "тепло", "холод", "климат",
            "климатический", "воздух", "воздушный поток",
            "температура помещения", "температура воздуха", "комната",
            "помещение", "мощность охлаждения", "хладагент", "фреон",
            "компрессор", "наружный блок", "внутренний блок",
            "внешний блок", "инверторный", "инвертор",
            "btu", "бту", "сплит",
        )
        return any(
            self._contains_phrase(text, keyword)
            for keyword in climate_context
        )
    # ==========================================================
    # BOOK TITLE
    # ==========================================================

    def _book_title(self, card):

        specs = getattr(card, "specs", {}) or {}

        fields = (
            "Название книги",
            "Название",
            "Наименование книги",
            "Наименование",
            "Заглавие",
            "Название произведения",
            "Произведение",
        )

        for field in fields:

            value = self._get_spec(
                specs,
                field
            )
            if value:
                return self._clean_book_title(value)
        title = str(
            getattr(card, "title", "")
            or ""
        ).strip()
        description = str(
            getattr(card, "description", "")
            or ""
        ).strip()

        for text in (title, description):

            if not text:
                continue

            match = re.search(
                r'(?:книга|учебник|роман|энциклопедия)'
                r'\s*["«„](.+?)["»“]',
                text,
                re.IGNORECASE
            )
            if match:
                return self._clean_book_title(
                    match.group(1)
                )

        # ФОЛБЭК: у подавляющего большинства продавцов заголовок товара
        # НЕ содержит кавычек вокруг названия ("книга «Название»") -
        if title:
            cleaned = self._clean_book_title(title)
            if cleaned:
                return cleaned

        return ""

    # ==========================================================
    # PUBLISHER
    # ==========================================================

    def _publisher(self, card):

        specs = getattr(card, "specs", {}) or {}

        fields = (
            "Издательство",
            "Издатель",
            "Издательская организация",
            "Издательство/издатель",
        )

        for field in fields:

            value = self._get_spec(
                specs,
                field
            )

            if value:
                return self._clean_value(value)

        # Более мягкий проход: любой ключ характеристики, где просто
        # ЕСТЬ подстрока "издат" (издательство/издатель/изд-во и т.п.) -
        # разные продавцы называют поле по-разному, а точное совпадение
        # выше ловит только самые распространённые варианты названия.
        for key, value in specs.items():

            if not value:
                continue

            if "издат" in str(key).lower() or "изд-во" in str(key).lower():
                return self._clean_value(value)

        title = str(
            getattr(card, "title", "")
            or ""
        )

        description = str(
            getattr(card, "description", "")
            or ""
        )

        text = f"{title} {description}"

        patterns = (
            r'издательство\s*["«„](.+?)["»“]',
            r'издатель\s*["«„](.+?)["»“]',
            r'издательство\s*[:\-]\s*([^,.;\n]+)',
            r'издатель\s*[:\-]\s*([^,.;\n]+)',
        )

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if match:
                return self._clean_value(
                    match.group(1)
                )

        # ФОЛБЭК: у WB/Ozon для книг отдельного поля "Издательство" в
        # характеристиках чаще всего просто НЕТ - вместо этого
        # издательство указано в общей характеристике "Бренд" (card.brand,
        # см. models/card_builder.py).
        brand = str(getattr(card, "brand", "") or "").strip()

        if brand:
            return self._clean_value(brand)

        return ""

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _text(self, card):

        parts = [
            getattr(card, "title", ""),
            getattr(card, "description", ""),
            getattr(card, "cleaned_text", ""),
            getattr(card, "slug", ""),
        ]

        specs = getattr(card, "specs", {}) or {}

        for key, value in specs.items():

            parts.append(str(key))
            parts.append(str(value))

        return " ".join(
            str(value)
            for value in parts
            if value
        ).lower()

    def _get_spec(self, specs, wanted):

        wanted = self._normalize_key(wanted)

        for key, value in specs.items():

            if self._normalize_key(key) == wanted:

                if value is None:
                    return ""

                return str(value).strip()

        return ""

    def _normalize_key(self, value):

        return re.sub(
            r"\s+",
            " ",
            str(value).strip().lower()
        )

    _BOOK_NOISE_PHRASES = (
        "новинка", "новинки", "хит продаж", "бестселлер",
        "топ продаж", "подарочное издание", "подарок",
        "оригинал", "лицензионный", "лицензионное",
        "акция", "скидка", "распродажа", "суперцена", "супер цена",
        "уценка", "уценённая", "уцененная",
    )

    def _clean_book_title(self, value):

        value = self._clean_value(value)

        value = re.sub(
            r'^(книга|учебник|роман)\s*[:\-]\s*',
            "",
            value,
            flags=re.IGNORECASE
        )

        for phrase in self._BOOK_NOISE_PHRASES:
            value = re.sub(
                r'(?<!\w)' + re.escape(phrase) + r'(?!\w)',
                "",
                value,
                flags=re.IGNORECASE,
            )

        value = re.sub(r"\s+", " ", value).strip(" ,.-–—")

        return value.strip()

    def _clean_value(self, value):

        value = str(value).strip()

        value = re.sub(
            r"\s+",
            " ",
            value
        )

        return value

    def _contains_phrase(self, text, phrase):

        pattern = r'(?<!\w)' + re.escape(phrase.lower()) + r'(?!\w)'
        return re.search(pattern, text) is not None
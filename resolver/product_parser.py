import re

from cleaner.product_extractor import ProductExtractor
from learning.name_normalizer import normalize_dictionary_name


class ProductParser:

    def __init__(self):

        self.extractor = ProductExtractor()

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def parse(self, card):

        texts = self.collect_texts(card)

        parsed = {
            "title": self.prepare(
                texts["title"]
            ),
            "slug": self.prepare(
                texts["slug"]
            ),
            "description": self.prepare(
                texts["description"]
            ),
            "cleaned_text": self.prepare(
                texts["cleaned_text"]
            ),
            "raw_text": self.prepare(
                texts["raw_text"]
            ),
            "specs": self.prepare(
                texts["specs"]
            ),
            "material": self.prepare(
                texts["material"]
            ),
            "brand": self.prepare(
                texts["brand"]
            ),
            "country": self.prepare(
                texts["country"]
            ),
            "quantity": texts["quantity"],
        }

        parsed["search_text"] = self.build_search_text(parsed)
        parsed["tokens"] = self.tokenize(parsed["search_text"])

        return parsed

    # ==========================================================
    # COLLECT
    # ==========================================================

    def collect_texts(self, card):

        specs = []

        for value in (card.specs or {}).values():

            if value:
                specs.append(str(value))

        return {

            "title":
                getattr(card, "title", ""),
            "slug":
                getattr(card, "slug", ""),
            "description":
                getattr(card, "description", ""),
            "cleaned_text":
                getattr(card, "cleaned_text", ""),
            "raw_text":
                getattr(card, "raw_text", ""),
            "specs":
                " ".join(specs),
            "material":
                getattr(card, "material", ""),
            "brand":
                getattr(card, "brand", ""),
            "country":
                getattr(card, "country", ""),
            "quantity":
                getattr(card, "quantity", ""),
        }

    # ==========================================================
    # NORMALIZE
    # ==========================================================

    def prepare(self, text):

        if not text:
            return ""

        text = normalize_dictionary_name(text)
        text = self.extractor.extract(text)

        return text.lower().strip()

    # ==========================================================
    # SEARCH TEXT
    # ==========================================================

    def build_search_text(self, parsed):

        parts = []

        for key in (
            "title",
            "slug",
            "description",
            "cleaned_text",
            "raw_text",
            "specs",
        ):

            value = parsed[key]

            if value:
                parts.append(value)

        return " ".join(parts)

    # ==========================================================
    # TOKENIZE
    # ==========================================================

    def tokenize(self, text):

        if not text:
            return set()

        text = re.sub(
            r"[^a-zа-я0-9 ]",
            " ",
            text,
            flags=re.IGNORECASE,
        )

        result = set()

        for word in text.split():

            word = word.strip()

            if len(word) < 3:
                continue

            if word.isdigit():
                continue

            result.add(word)

        return result
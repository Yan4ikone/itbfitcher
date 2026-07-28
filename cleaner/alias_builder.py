from cleaner.product_cleaner import clean_text
from cleaner.product_extractor import ProductExtractor
from classifier.normalizer import normalize_name


class AliasBuilder:

    def __init__(self):

        self.extractor = ProductExtractor()

    # ======================================================
    # PUBLIC
    # ======================================================

    def build(self, card, description):

        aliases = set()

        for text in (
            card.get("title", ""),
            card.get("slug", ""),
        ):

            aliases |= self._extract_aliases(text)

        aliases.discard("")
        aliases.discard(description.lower())

        return sorted(aliases)

    # ======================================================
    # INTERNAL
    # ======================================================

    def _extract_aliases(self, text):

        aliases = set()

        if not text:
            return aliases

        text, _, _ = clean_text(text)
        normalized = normalize_name(text).lower().strip()

        if normalized:
            aliases.add(normalized)

        short = self.extractor.extract(text)

        if short:
            aliases.add(short.lower())

        if len(short.split()) > 1:

            aliases.add(short.split()[0])

        return aliases
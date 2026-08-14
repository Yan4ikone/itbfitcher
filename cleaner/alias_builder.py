import re

from cleaner.product_cleaner import clean_text
from cleaner.product_extractor import ProductExtractor
from classifier.normalizer import normalize_name
from dictionaries.all_dictionaries import IGNORED_ALIAS_WORDS, TRASH_MARKETING, TRASH_MARKETPLACE, TRASH_PACKAGE


class AliasBuilder:

    def __init__(self):

        self.extractor = ProductExtractor()
    # ======================================================
    # PUBLIC
    # ======================================================
    def build(self, card, description):

        aliases = set()
        description = (normalize_name(description or "")
            .lower()
            .strip()
        )
        for text in (
            card.get("title", ""),
            card.get("slug", ""),
        ):
            aliases.update(self._extract_aliases(text))
        aliases.discard("")
        aliases.discard(description)

        return sorted(aliases)
    # ======================================================
    # INTERNAL
    # ======================================================
    def _extract_aliases(self, text):

        if not text:
            return set()

        text, _, _ = clean_text(text)
        normalized = (normalize_name(text)
            .lower()
            .strip()
        )
        short = self.extractor.extract(text)
        candidates = set()

        if normalized:
            candidates.add(normalized)
        if short:
            candidates.add(short.lower().strip())
        if len(short.split()) > 1:
            candidates.add(normalize_name(short.split()[0])
                .lower()
                .strip()
            )
        result = set()

        for alias in candidates:

            alias = self._clean_alias(alias)

            if not alias:
                continue
            if not self._is_valid_alias(alias):
                continue

            result.add(alias)

        return result
    # ======================================================
    # CLEAN
    # ======================================================
    def _clean_alias(self, alias):

        words = alias.lower().strip().split()

        if not words:
            return ""

        cleaned_words = []

        for word in words:

            word = word.strip(".,;:!?()[]{}\"'«»")

            if not word:
                continue
            if word in IGNORED_ALIAS_WORDS:
                continue
            if word in TRASH_MARKETING:
                continue
            if word in TRASH_MARKETPLACE:
                continue
            if word in TRASH_PACKAGE:
                continue

            cleaned_words.append(word)

        return " ".join(cleaned_words)
        # ======================================================
        # FILTER
        # ======================================================

    def _is_valid_alias(self, alias):

        alias = alias.lower().strip()

        if not alias:
            return False

        words = alias.split()

        if not words:
            return False

        if all(
                word in (
                        IGNORED_ALIAS_WORDS
                        | TRASH_MARKETING
                        | TRASH_MARKETPLACE
                        | TRASH_PACKAGE
                )
                for word in words
        ):
            return False

        if len(words) == 1 and len(words[0]) < 4:
            return False
        if all(
                re.fullmatch(
                    r"\d+(?:[.,]\d+)?",
                    word
                )
                for word in words
        ):
            return False
        if any(
                word in (
                        "шт",
                        "штук",
                        "см",
                        "мм",
                        "мл",
                        "л",
                        "кг",
                        "г",
                )
                for word in words
        ):
            return False
        return True
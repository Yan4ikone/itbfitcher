import re

from cleaner.product_cleaner import clean_text
from dictionaries.all_dictionaries import REMOVE_WORDS, KEEP_PREPOSITIONS, KEEP_UNITS

STOP_WORDS = REMOVE_WORDS | {
    "цвет",
    "модель",
    "размер",
    "артикул",
    "оригинал",
    "универсальный",
    "профессиональный",
}

class ProductExtractor:

    def extract(self, text: str) -> str:

        cleaned, _, _ = clean_text(text)
        cleaned = cleaned.lower()
        cleaned = self._remove_negative(cleaned)
        cleaned = self._remove_brackets(cleaned)
        cleaned = self._remove_sizes(cleaned)
        cleaned = self._remove_dimensions(cleaned)
        cleaned = self._remove_article(cleaned)
        cleaned = self._normalize_spaces(cleaned)

        words = cleaned.split()
        result = []

        for word in words:

            if self._skip_word(word):
                continue

            result.append(word)
        result = self._trim_tail(result)

        return " ".join(result).strip()

    # =====================================================
    def _remove_negative(self, text):

        return re.sub(
            r"\bбез\s+\w+\b",
            " ",
            text
        )


    def _skip_word(self, word):

        if not word:
            return True

        if word in KEEP_PREPOSITIONS:
            return False

        if word in KEEP_UNITS:
            return False

        if word in STOP_WORDS:
            return True

        if word.isdigit():
            return True

        if any(ch.isdigit() for ch in word):

            if word in KEEP_UNITS:
                return False

            return True

        return False

    # =====================================================

    def _trim_tail(self, words):

        while words:

            last = words[-1]

            if last in KEEP_UNITS:
                break

            if len(last) <= 2:
                words.pop()
                continue

            break

        return words

    # =====================================================

    def _remove_brackets(self, text):

        return re.sub(r"\(.*?\)", " ", text)

    # =====================================================

    def _remove_sizes(self, text):

        text = re.sub(
            r"\b\d+[.,]?\d*\s?(см|мм|м|л|мл|кг|г|гр)\b",
            " ",
            text,
        )

        text = re.sub(
            r"\b\d+[xх]\d+([xх]\d+)?\b",
            " ",
            text,
        )

        return text

    # =====================================================

    def _remove_dimensions(self, text):

        text = re.sub(
            r"\b\d+\s?дюйм(ов|а|)\b",
            " ",
            text,
        )

        return text

    # =====================================================

    def _remove_article(self, text):

        return re.sub(
            r"\b[a-zа-я]*\d+[a-zа-я\d\-]*\b",
            " ",
            text,
        )

    # =====================================================

    def _normalize_spaces(self, text):

        return re.sub(r"\s+", " ", text).strip()
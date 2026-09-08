from collections import Counter
from difflib import SequenceMatcher

from cleaner.morphology import Morphology
from cleaner.product_extractor import ProductExtractor
from learning.name_normalizer import normalize_dictionary_name


class ProductMatcher:

    # Пороги подобраны по реальному распределению products.py
    _GENERIC_CODE_FULL_BONUS_UPTO = 8
    _GENERIC_CODE_ZERO_BONUS_FROM = 20

    def __init__(self, repository):
        self.repository = repository
        self.extractor = ProductExtractor()
        self.morphology = Morphology()

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def match(self, description, code):

        description = self.extractor.extract(description)

        all_products = list(self.repository.all())

        code_counts = Counter(
            str(info.get("code") or "").strip()
            for _, info in all_products
        )

        best_product = None
        best_score = 0

        for product, info in all_products:

            score = self.score(description, code, product, info, code_counts)

            if score > best_score:
                best_score = score
                best_product = product

        if best_score < 60:
            return None

        return {
            "product": best_product,
            "score": best_score,
        }

    # ==========================================================
    # КОД: МАСШТАБИРОВАННЫЙ БОНУС
    # ==========================================================

    def _code_bonus(self, code, full_bonus, code_counts):
        """Полный бонус только если код действительно "принадлежит"
        узкому кругу товаров. Пустой код и "0" (незаполненный/
        плейсхолдер) бонуса не дают вообще."""

        code = str(code or "").strip()

        if not code or code == "0":
            return 0

        shared = code_counts.get(code, 0) if code_counts else 1

        if shared <= self._GENERIC_CODE_FULL_BONUS_UPTO:
            return full_bonus

        if shared >= self._GENERIC_CODE_ZERO_BONUS_FROM:
            return 0

        # Линейное затухание между "ещё нормально" и "уже свалка".
        span = self._GENERIC_CODE_ZERO_BONUS_FROM - self._GENERIC_CODE_FULL_BONUS_UPTO
        fraction = 1 - (shared - self._GENERIC_CODE_FULL_BONUS_UPTO) / span

        return int(full_bonus * fraction)

    def score(self, description, code, product, info, code_counts=None):
        score = 0

        if str(info.get("code")) == str(code):
            score += self._code_bonus(code, 40, code_counts)

        # ------------------------------------------------------
        # Название товара
        # ------------------------------------------------------

        score = max(
            score,
            self._product_score(description, code, product, info, code_counts),
        )

        # ------------------------------------------------------
        # Алиасы
        # ------------------------------------------------------

        for alias in info.get("aliases", []):

            score = max(
                score,
                self._alias_score(description, alias, code, info, code_counts),
            )

        # ------------------------------------------------------
        # Score words
        # ------------------------------------------------------

        score = max(
            score,
            self._score_words_score(
                description,
                code,
                info,
                code_counts,
            ),
        )

        return min(score, 100)

    # ==========================================================
    # PRODUCT SCORE
    # ==========================================================

    def _product_score(self, description, code, product, info, code_counts=None):

        score = 0

        if str(info.get("code")) == str(code):
            score += self._code_bonus(code, 40, code_counts)

        score += self._word_score(description, product)
        score += self._similarity_score(description, product)

        return score

    # ==========================================================
    # ALIAS SCORE
    # ==========================================================

    def _alias_score(self, description, alias, code, info, code_counts=None):

        score = 0

        if str(info.get("code")) == str(code):
            score += self._code_bonus(code, 30, code_counts)

        score += self._word_score(description, alias)
        score += self._similarity_score(description, alias)

        return score

    # ==========================================================
    # SCORE WORDS
    # ==========================================================

    def _score_words_score(self, description, code, info, code_counts=None):

        score = 0

        if str(info.get("code")) == str(code):
            score += self._code_bonus(code, 20, code_counts)

        score_words = info.get("score_words", [])

        if not score_words:
            return score

        left = self.tokenize(description)
        right = {
            normalize_dictionary_name(word)
            for word in score_words
        }
        common = left & right

        if common:
            ratio = len(common) / len(right)
            score += int(ratio * 50)
        return score

    # ==========================================================
    # WORD SCORE
    # ==========================================================

    def _word_score(self, left, right):

        left_words = {self.morphology.normal(word)
            for word in self.tokenize(left)
        }
        right_words = {self.morphology.normal(word)
            for word in self.tokenize(right)
        }

        if not left_words or not right_words:
            return 0

        common = left_words & right_words

        if not common:
            return 0

        ratio = (
                len(common)
                / max(
            len(left_words),
            len(right_words),
        )
        )

        return int(ratio * 50)

    # ==========================================================
    # STRING SIMILARITY
    # ==========================================================

    def _similarity_score(self, left, right):

        left = normalize_dictionary_name(left)
        right = normalize_dictionary_name(right)
        similarity = SequenceMatcher(None, left, right).ratio()

        return int(similarity * 20)

    # ==========================================================
    # TOKENIZE
    # ==========================================================

    def tokenize(self, text):

        text = normalize_dictionary_name(text)

        return {
            word
            for word in text.lower().split()
            if len(word) > 2
            and not word.isdigit()
        }
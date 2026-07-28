from difflib import SequenceMatcher

from cleaner.morphology import Morphology
from cleaner.product_extractor import ProductExtractor
from learning.name_normalizer import normalize_dictionary_name


class ProductMatcher:

    def __init__(self, repository):
        self.repository = repository
        self.extractor = ProductExtractor()
        self.morphology = Morphology()

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def match(self, description, code):

        description = self.extractor.extract(description)
        best_product = None
        best_score = 0

        for product, info in self.repository.all():

            score = self.score(description, code, product, info)

            if score > best_score:
                best_score = score
                best_product = product

        if best_score < 60:
            return None

        return {
            "product": best_product,
            "score": best_score,
        }


    def score(self, description, code, product, info):
        score = 0

        if str(info.get("code")) == str(code):
            score += 40

        # ------------------------------------------------------
        # Название товара
        # ------------------------------------------------------

        score = max(score, self._product_score(description, code, product, info),)

        # ------------------------------------------------------
        # Алиасы
        # ------------------------------------------------------

        for alias in info.get("aliases", []):

            score = max(score, self._alias_score(description, alias, code, info),)

        # ------------------------------------------------------
        # Score words
        # ------------------------------------------------------

        score = max(
            score,
            self._score_words_score(
                description,
                code,
                info,
            ),
        )

        return min(score, 100)

    # ==========================================================
    # PRODUCT SCORE
    # ==========================================================

    def _product_score(self, description, code, product, info):

        score = 0

        if str(info.get("code")) == str(code):
            score += 40

        score += self._word_score(description, product)
        score += self._similarity_score(description, product)

        return score

    # ==========================================================
    # ALIAS SCORE
    # ==========================================================

    def _alias_score(self, description, alias, code, info):

        score = 0

        if str(info.get("code")) == str(code):
            score += 30

        score += self._word_score(description, alias)
        score += self._similarity_score(description, alias)

        return score

    # ==========================================================
    # SCORE WORDS
    # ==========================================================

    def _score_words_score(self, description, code, info):

        score = 0

        if str(info.get("code")) == str(code):
            score += 20

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
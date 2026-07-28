from functools import lru_cache

import pymorphy3


class Morphology:

    def __init__(self):

        self.morph = pymorphy3.MorphAnalyzer()

    # =====================================================
    # NORMAL FORM
    # =====================================================

    @lru_cache(maxsize=100000)
    def normal(self, word: str) -> str:

        if not word:
            return ""

        return self.morph.parse(word)[0].normal_form

    # =====================================================
    # POS
    # =====================================================

    @lru_cache(maxsize=100000)
    def pos(self, word: str) -> str:

        if not word:
            return ""

        tag = self.morph.parse(word)[0].tag.POS

        return tag or ""

    # =====================================================
    # CHECKS
    # =====================================================

    def is_noun(self, word):
        return self.pos(word) == "NOUN"

    def is_adj(self, word):
        return self.pos(word) == "ADJF"

    def is_participle(self, word):
        return self.pos(word) == "PRTF"

    def is_verb(self, word):
        return self.pos(word) in {"VERB","INFN"}

    def is_numeral(self, word):
        return self.pos(word) == "NUMR"

    # =====================================================
    # TOKENIZE
    # =====================================================

    def normalize_words(self, words):

        result = []

        for word in words:

            normal = self.normal(word)

            if normal:
                result.append(normal)

        return result

    # =====================================================
    # IMPORTANT WORDS
    # =====================================================

    def important_words(self, words):

        result = []

        for word in words:

            pos = self.pos(word)

            if pos in {
                "NOUN",
                "ADJF",
            }:
                result.append(self.normal(word))

        return result

    # =====================================================
    # COMPARE
    # =====================================================

    def same_word(self, left, right):
        return self.normal(left) == self.normal(right)
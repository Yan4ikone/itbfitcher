from difflib import SequenceMatcher

from learning.name_normalizer import normalize_dictionary_name


class CandidateScorer:

    def __init__(self, repository):

        self.repository = repository

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def score(self, candidate, parsed):

        info = candidate.info
        self._score_product(candidate, parsed, candidate.product)

        for alias in info.get("aliases", []):
            self._score_alias(candidate, parsed, alias)
        for pattern in info.get("patterns", []):

            self._score_pattern(candidate, parsed, pattern)
        self._score_words(candidate, parsed, info.get("score_words", []))
        self._apply_penalties(candidate)

        return candidate

    # ==========================================================
    # PRODUCT
    # ==========================================================

    def _score_product(self, candidate, parsed, product):

        self._field_score(candidate, parsed["title"], product,250,"TITLE")
        self._field_score(candidate, parsed["slug"], product,220,"SLUG")
        self._field_score(candidate, parsed["description"], product,200,"DESCRIPTION")
        self._field_score(candidate, parsed["cleaned_text"], product,350,"CLEANED")
        for value in parsed["specs_dict"].values():
            self._field_score(candidate, value, product,150,"SPECS")

    # ==========================================================
    # ALIAS
    # ==========================================================

    def _score_alias(self, candidate, parsed,alias):

        self._field_score(candidate, parsed["title"], alias,300,"TITLE_ALIAS")
        self._field_score(candidate, parsed["slug"], alias,220,"SLUG_ALIAS")
        self._field_score(candidate, parsed["description"], alias,300,"DESC_ALIAS")
        self._field_score(candidate, parsed["cleaned_text"], alias,250,"CLEANED_ALIAS")

    # ==========================================================
    # PATTERN
    # ==========================================================

    def _score_pattern(self, candidate, parsed, pattern):

        import re

        try:
            if re.search(pattern, parsed["search_text"]):
                candidate.add("PATTERN", 350, pattern)
        except re.error:
            return

    # ==========================================================
    # SCORE WORDS
    # ==========================================================

    def _score_words(self, candidate, parsed, score_words):

        if not score_words:
            return

        tokens = parsed["tokens"]

        for word in score_words:

            if word.lower() in tokens:

                candidate.add("SCORE_WORD", 40, word)

    # ==========================================================
    # FIELD SCORE
    # ==========================================================

    def _field_score(self, candidate, text, phrase, weight, source):

        if not text:
            return

        phrase = normalize_dictionary_name(phrase).lower()

        if phrase in text:

            candidate.add(source, weight, phrase)

            return

        similarity = SequenceMatcher(
            None,
            text,
            phrase,
        ).ratio()

        if similarity > 0.85:

            candidate.add(
                source + "_SIMILAR",
                int(weight * similarity * 0.4),
                phrase,
            )

    # ==========================================================
    # PENALTIES
    # ==========================================================

    def _apply_penalties(self, candidate):

        breakdown = candidate.breakdown
        title = breakdown.get("TITLE", 0)
        slug = breakdown.get("SLUG", 0)
        desc = breakdown.get("DESCRIPTION", 0)

        if title == 0 and slug == 0:
            candidate.score -= 500
        if desc > 0 and title == 0:
            candidate.score -= 250
        if candidate.score < 0:
            candidate.score = 0
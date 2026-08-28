from difflib import SequenceMatcher
from learning.name_normalizer import normalize_dictionary_name

import re


class CandidateScorer:

    def __init__(self, repository):

        self.repository = repository
    # ==============================================================
    # PUBLIC
    # ==============================================================
    def score(self, candidate, parsed, specs_weight=150):

        normalized = {
            "title": normalize_dictionary_name(parsed["title"]).lower().strip(),
            "slug": normalize_dictionary_name(parsed["slug"]).lower().strip(),
            "description": normalize_dictionary_name(parsed["description"]).lower().strip(),
            "cleaned_text": normalize_dictionary_name(parsed["cleaned_text"]).lower().strip(),
        }
        prepared = {**parsed, **normalized}
        info = candidate.info
        self._score_product(
            candidate,
            prepared,
            candidate.product,
            specs_weight,
        )
        for alias in info.get("aliases", []):
            self._score_alias(candidate, prepared, alias)

        for pattern in info.get("patterns", []):
            self._score_pattern(candidate, parsed, pattern)
        self._score_words(candidate, parsed, info.get("score_words", []))
        # При обычном скоринге specs_weight=150 (штраф за отсутствие
        # TITLE/SLUG применяется в полную силу). При доразборе
        # неоднозначных карточек (specs_weight усилен) штраф смягчаем -
        # именно тогда SPECS/доп.описание и должны иметь шанс перевесить.
        self._apply_penalties(candidate, relaxed=specs_weight > 150)

        return candidate
    # ==============================================================
    # PRODUCT
    # ==============================================================
    def _score_product(self, candidate, parsed, product, specs_weight=150):

        self._field_score(
            candidate,
            parsed["title"],
            product,
            250,
            "TITLE",
        )
        self._field_score(
            candidate,
            parsed["slug"],
            product,
            220,
            "SLUG",
        )
        self._field_score(
            candidate,
            parsed["description"],
            product,
            200,
            "DESCRIPTION"
        )
        self._field_score(
            candidate,
            parsed["cleaned_text"],
            product,
            350,
            "CLEANED",
        )
        type_keys = ("тип", "тип товара")

        for key, value in parsed["specs_dict"].items():

            if str(key).strip().lower() in type_keys:
                self._field_score(
                    candidate,
                    value,
                    product,
                    300,
                    "SPEC_TYPE",
                )
        for value in parsed["specs_dict"].values():

            # specs_weight усиливается при повторном скоринге
            self._field_score(
                candidate,
                value,
                product,
                specs_weight,
                "SPECS",
            )
        for crumb in parsed.get("breadcrumbs", []):
            self._field_score(
                candidate,
                crumb,
                product,
                180,
                "BREADCRUMB",
            )
    # ==============================================================
    # ALIAS
    # ==============================================================
    def _score_alias(self, candidate, parsed, alias):

        self._field_score(
            candidate,
            parsed["title"],
            alias,
            300,
            "TITLE_ALIAS",
        )
        self._field_score(
            candidate,
            parsed["slug"],
            alias,
            220,
            "SLUG_ALIAS",
        )
        self._field_score(
            candidate,
            parsed["description"],
            alias,
            300,
            "DESC_ALIAS",
        )
        self._field_score(
            candidate,
            parsed["cleaned_text"],
            alias,
            250,
            "CLEANED_ALIAS",
        )
    # ==============================================================
    # PATTERN
    # ==============================================================
    def _score_pattern(self, candidate, parsed, pattern):

        try:
            if re.search(pattern, parsed["search_text"]):

                candidate.add("PATTERN", 350, pattern)

        except re.error:
            return
    # ==============================================================
    # SCORE WORDS
    # ==============================================================
    def _score_words(self, candidate, parsed, score_words):

        if not score_words:
            return

        tokens = parsed["tokens"]

        for word in score_words:
            if word.lower() in tokens:

                candidate.add("SCORE_WORD", 40, word)
    # ==============================================================
    # FIELD SCORE
    # ==============================================================
    def _field_score(self, candidate, text, phrase, weight, source):

        if not text or not phrase:
            return

        text = text.lower()
        phrase = phrase.lower()
        # -------------------------------------------------
        # Быстрый поиск точного совпадения
        # -------------------------------------------------
        if phrase in text:

            candidate.add(source, weight, phrase)

            return

        words = phrase.split()

        if len(words) > 1:

            gap_pattern = (
                    r"\b" + r"\b\W+(?:\S+\W+){0,2}".join(
                re.escape(word) for word in words) + r"\b")

            try:
                if re.search(gap_pattern, text):
                    candidate.add(source, weight, phrase)
                    return
            except re.error:
                pass
        # -------------------------------------------------
        # Нечёткий поиск только для коротких строк
        # -------------------------------------------------
        if len(text) > 300:
            return

        similarity = SequenceMatcher(None, text, phrase).ratio()

        if similarity > 0.85:
            candidate.add(
                source + "_SIMILAR",
                int(weight * similarity * 0.4),
                phrase
            )
    # ==============================================================
    # PENALTIES
    # ==============================================================
    def _apply_penalties(self, candidate, relaxed=False):

        breakdown = candidate.breakdown
        title = breakdown.get("TITLE", 0)
        slug = breakdown.get("SLUG", 0)
        desc = breakdown.get("DESCRIPTION", 0)
        specs = breakdown.get("SPECS", 0)

        if title == 0 and slug == 0:
            if relaxed and specs > 0:
                # Доразбор: нет совпадения в заголовке, но есть явное
                # совпадение в характеристиках/доп.описании - не убиваем
                # кандидата штрафом целиком, а лишь ослабляем его.
                candidate.score -= 150
            else:
                candidate.score -= 500
        if desc > 0 and title == 0:
            candidate.score -= 250
        if candidate.score < 0:
            candidate.score = 0
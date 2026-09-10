from difflib import SequenceMatcher
from learning.name_normalizer import normalize_dictionary_name
from utils.tokenizer import lemmatized_tokens

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
        self._score_aliases(candidate, prepared, info.get("aliases", []))

        self._score_patterns(candidate, parsed, info.get("patterns", []))
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
    def _score_aliases(self, candidate, parsed, aliases):
        """Как и с паттернами (_score_patterns) - несколько РАЗНЫХ
        алиасов одного товара, совпавших в одном и том же поле, всё
        ещё описывают ОДИН факт "текст похож на этот товар", а не
        независимые улики. Раньше каждый совпавший алиас добавлял
        очки НЕЗАВИСИМО (суммируясь) - например, если описание
        одновременно упоминало "кеды" и "кроссовки" (оба - алиасы
        товара "кроссовки"), это давало двойной счёт (300+300=600) и
        позволяло случайному перечислению ("подходит для кроссовок,
        туфель, кед") обогнать товар, чьё название БУКВАЛЬНО совпадает
        с заголовком карточки. Теперь на каждое поле берётся ЛУЧШЕЕ
        совпадение среди всех алиасов, не более одного раза."""

        if not aliases:
            return

        fields = (
            ("title", 300, "TITLE_ALIAS"),
            ("slug", 220, "SLUG_ALIAS"),
            ("description", 300, "DESC_ALIAS"),
            ("cleaned_text", 250, "CLEANED_ALIAS"),
        )

        for field_key, weight, source in fields:

            text = parsed[field_key]

            best = None  # (matched_weight, is_similar, alias)

            for alias in aliases:

                result = self._match_weight(text, alias, weight)

                if result is None:
                    continue

                matched_weight, is_similar = result

                if best is None or matched_weight > best[0]:
                    best = (matched_weight, is_similar, alias)

            if best:

                matched_weight, is_similar, alias = best

                candidate.add(
                    source + ("_SIMILAR" if is_similar else ""),
                    matched_weight,
                    alias,
                )
    # ==============================================================
    # PATTERN
    # ==============================================================
    def _score_patterns(self, candidate, parsed, patterns):
        """PATTERN засчитывается НЕ БОЛЕЕ ОДНОГО РАЗА за кандидата,
        даже если совпало несколько его паттернов - несколько
        паттернов ("комбинез" и "комбинез.*") обычно описывают один и
        тот же факт (альтернативные способы поймать одно и то же
        слово), а не независимые улики. Раньше каждый совпавший
        паттерн добавлял +350 отдельно (Candidate.add суммирует по
        reason), из-за чего товар с двумя перекрывающимися паттернами
        получал вдвое больше веса без всякого основания."""

        matched_pattern = None
        match_start = None

        for pattern in patterns:

            try:
                match = re.search(pattern, parsed["search_text"])
                if match:
                    matched_pattern = pattern
                    match_start = match.start()
                    break
            except re.error:
                continue

        if matched_pattern:

            weight = 350

            if match_start is not None and match_start > 0:

                text = parsed["search_text"]
                preceding = text[:match_start].rstrip()

                for prep in self._CONTEXT_PREPOSITIONS:
                    if preceding == prep or preceding.endswith(" " + prep):
                        weight = int(weight * 0.25)
                        break

            candidate.add("PATTERN", weight, matched_pattern)
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
    # Предлоги, после которых слово почти всегда вводит МОДИФИКАТОР
    # ("подушка НА стул", "чехол ДЛЯ телефона", "крепление ПОД
    # степлер") - то есть аксессуар/деталь ДЛЯ X, а не сам товар X.
    # Без этой поправки "стул" в "подушка на стул" получал тот же вес,
    # что и "подушка", хотя грамматически "стул" здесь - явно не то,
    # что продаётся.
    _CONTEXT_PREPOSITIONS = ("для", "на", "под", "от", "к")

    def _field_score(self, candidate, text, phrase, weight, source):

        result = self._match_weight(text, phrase, weight)

        if result is None:
            return

        matched_weight, is_similar = result

        candidate.add(
            source + ("_SIMILAR" if is_similar else ""),
            matched_weight,
            phrase,
        )

    def _match_weight(self, text, phrase, weight):
        """Вычисляет вес совпадения БЕЗ начисления очков кандидату -
        отдельно от _field_score, чтобы можно было найти ЛУЧШЕЕ
        совпадение среди НЕСКОЛЬКИХ фраз (см. _score_aliases) и
        начислить очки только один раз, а не за каждую фразу отдельно.

        Возвращает (вес, признак_нечёткого_совпадения) или None, если
        совпадения нет вообще."""

        if not text or not phrase:
            return None

        text = text.lower()
        phrase = phrase.lower()
        # -------------------------------------------------
        # Быстрый поиск точного совпадения - С ГРАНИЦАМИ СЛОВА.
        # -------------------------------------------------
        try:
            if re.search(
                r"(?<!\w)" + re.escape(phrase) + r"(?!\w)",
                text,
            ):

                weight = self._weaken_if_modifier_context(text, phrase, weight)

                return weight, False

        except re.error:
            pass

        words = phrase.split()

        if len(words) > 1:

            gap_pattern = (
                    r"\b" + r"\b\W+(?:\S+\W+){0,2}".join(
                re.escape(word) for word in words) + r"\b")

            try:
                if re.search(gap_pattern, text):
                    weight = self._weaken_if_modifier_context(text, phrase, weight)
                    return weight, False
            except re.error:
                pass

        # -------------------------------------------------
        # Лемматизированное сравнение - словоформы могут отличаться
        # ("мягкая игрушка" в словаре vs "Мягкие игрушки" в категории
        # с маркетплейса - грамматически разные формы одного и того
        # же). Проверяем, что ВСЕ леммы фразы встречаются среди лемм
        # текста, а не только буквальное вхождение подстроки.
        # -------------------------------------------------

        phrase_lemmas = lemmatized_tokens(phrase)

        if phrase_lemmas:

            text_lemmas = lemmatized_tokens(text)

            if phrase_lemmas <= text_lemmas:
                # Ослабляем сильнее, чем при точном совпадении - это
                # менее строгая проверка (без учёта порядка/близости
                # слов), поэтому не даём ей полный вес. Плюс отдельно
                # проверяем предлог-модификатор ПО ЛЕММЕ -
                # text.find(phrase) здесь не сработал бы: в тексте
                # стоит другая словоформа ("газонокосилки", а не
                # "газонокосилка" из словаря), обычный поиск подстроки
                # её не находит вообще.
                weight = self._weaken_if_modifier_context_lemma(
                    text, phrase_lemmas, weight
                )
                return int(weight * 0.6), False

        # -------------------------------------------------
        # Нечёткий поиск только для коротких строк
        # -------------------------------------------------
        if len(text) > 300:
            return None

        similarity = SequenceMatcher(None, text, phrase).ratio()

        if similarity > 0.85:
            return int(weight * similarity * 0.4), True

        return None

    def _weaken_if_modifier_context(self, text, phrase, weight):
        """Если фраза стоит сразу после предлога-модификатора
        ("на"/"для"/"под"/"от"/"к"), она почти наверняка описывает,
        ДЛЯ ЧЕГО нужен товар, а не сам товар - ослабляем вес, но не
        обнуляем полностью (иногда единственное упоминание всё же
        верное)."""

        pos = text.find(phrase)

        if pos <= 0:
            return weight

        preceding = text[:pos].rstrip()

        for prep in self._CONTEXT_PREPOSITIONS:
            if preceding == prep or preceding.endswith(" " + prep):
                return int(weight * 0.25)

        return weight

    def _weaken_if_modifier_context_lemma(self, text, phrase_lemmas, weight):
        """Как _weaken_if_modifier_context, но для лемматизированного
        совпадения - в тексте стоит другая словоформа ("газонокосилки"
        вместо "газонокосилка" из словаря), обычный text.find(phrase)
        её не находит вообще, поэтому штраф за предлог-модификатор
        никогда не применялся к этому пути. Ищем слово по лемме и
        проверяем предлог перед НИМ, а не перед точной фразой."""

        words = text.split()

        for i, word in enumerate(words):

            word_clean = word.strip(".,!?;:()\"'«»-")

            if not word_clean:
                continue

            word_lemma = next(
                iter(lemmatized_tokens(word_clean)),
                None,
            )

            if word_lemma and word_lemma in phrase_lemmas:

                if i == 0:
                    return weight

                preceding = words[i - 1].strip(".,!?;:()\"'«»-").lower()

                if preceding in self._CONTEXT_PREPOSITIONS:
                    return int(weight * 0.25)

                return weight

        return weight
    # ==============================================================
    # PENALTIES
    # ==============================================================
    def _apply_penalties(self, candidate, relaxed=False):

        breakdown = candidate.breakdown
        title = breakdown.get("TITLE", 0)
        slug = breakdown.get("SLUG", 0)
        desc = breakdown.get("DESCRIPTION", 0)
        specs = breakdown.get("SPECS", 0)
        breadcrumb = breakdown.get("BREADCRUMB", 0)

        if title == 0 and slug == 0:
            if breadcrumb > 0:
                # Категория/подкатегория с маркетплейса - надёжный
                # сигнал сам по себе, даже когда заголовок - сплошной
                candidate.score -= 150
            elif relaxed and specs > 0:
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
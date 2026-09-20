from difflib import SequenceMatcher
from learning.name_normalizer import normalize_dictionary_name
from utils.tokenizer import lemmatized_tokens, word_case

import re


class CandidateScorer:

    def __init__(self, repository):

        self.repository = repository
    # ==============================================================
    # PUBLIC
    # ==============================================================
    def score(self, candidate, parsed, specs_weight=150):

        info = candidate.info
        # ------------------------------------------------------------
        # ДОБАВЛЕНО: "requires_context" - для словарных слов с двумя
        # никак не связанными бытовыми значениями (пример: "прокладки"
        # без уточнения - раньше ВСЕГДА уходило в код женских
        # гигиенических прокладок, даже когда слово встречалось в
        # чисто техническом контексте - "Прокладка" в наборе резиновых
        # кабельных втулок для электрощита; разбор - products-dict-
        # gradation-audit.md). Если у товара задан этот список слов -
        # кандидат вообще НЕ участвует в подборе кода, пока рядом в
        # тексте карточки нет ни одного из этих слов (женские/
        # гигиенические/ежедневные и т.п.) - тогда это, скорее всего,
        # другой, технический смысл того же слова, и нужно смотреть
        # другие кандидаты, а не угадывать этот код по умолчанию.
        # ------------------------------------------------------------
        required_context = info.get("requires_context")

        if required_context:

            haystack = parsed.get("search_text", "") or ""

            if not any(word in haystack for word in required_context):
                return candidate

        normalized = {
            "title": normalize_dictionary_name(parsed["title"]).lower().strip(),
            "slug": normalize_dictionary_name(parsed["slug"]).lower().strip(),
            "description": normalize_dictionary_name(parsed["description"]).lower().strip(),
            "cleaned_text": normalize_dictionary_name(parsed["cleaned_text"]).lower().strip(),
            "image_description": normalize_dictionary_name(
                parsed.get("image_description", "")
            ).lower().strip(),
        }
        prepared = {**parsed, **normalized}
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
        # Описание с картинки (получено через ИИ-распознавание -
        # см. processors/card_image_processor.py) - запрашивается
        # ТОЛЬКО когда обычный текст уже не дал результата, поэтому
        # это целевой, надёжный сигнал. Вес - наравне с CLEANED
        # (максимальный среди обычных полей), а не как рядовое
        # дополнение к описанию.
        self._field_score(
            candidate,
            parsed.get("image_description", ""),
            product,
            350,
            "IMAGE_DESC",
        )
        type_keys = ("тип", "тип товара")

        self._best_field_score(
            candidate,
            (
                value
                for key, value in parsed["specs_dict"].items()
                if str(key).strip().lower() in type_keys
            ),
            product,
            300,
            "SPEC_TYPE",
        )
        # specs_weight усиливается при повторном скоринге (доразбор)
        self._best_field_score(
            candidate,
            parsed["specs_dict"].values(),
            product,
            specs_weight,
            "SPECS",
        )
        self._best_field_score(
            candidate,
            parsed.get("breadcrumbs", []),
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
            ("image_description", 350, "IMAGE_DESC_ALIAS"),
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
        match_end = None

        for pattern in patterns:

            try:
                match = re.search(pattern, parsed["search_text"])
                if match:
                    matched_pattern = pattern
                    match_start = match.start()
                    match_end = match.end()
                    break
            except re.error:
                continue

        if matched_pattern:

            weight = 350

            if match_start is not None and match_start > 0:

                text = parsed["search_text"]
                preceding = text[:match_start].rstrip()
                following = text[match_end:].lstrip()

                for prep in self._CONTEXT_PREPOSITIONS:
                    if preceding == prep or preceding.endswith(" " + prep):
                        weight = int(weight * 0.25)
                        break
                else:
                    if (
                            preceding.endswith(",")
                            or preceding.endswith(" или")
                            or following.startswith(",")
                            or following.startswith("или ")
                    ):
                        weight = int(weight * 0.25)

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

    def _best_field_score(self, candidate, texts, phrase, weight, source):
        """Как _score_aliases - несколько текстов одной и той же
        природы (несколько значений specs_dict, несколько уровней
        breadcrumb), совпавших с ОДНИМ и тем же названием товара, всё
        ещё описывают ОДИН факт "где-то на странице упомянут этот
        товар", а не независимые улики. Раньше _field_score вызывался
        в цикле для КАЖДОГО значения отдельно, и Candidate.add
        суммировал очки без ограничения - на реальном прогоне
        (Test_machine_2, 2026-09-18) это дало SPECS=450 (150x3) для
        карточки, где совпадение было по сути одно и то же значение
        характеристики, повторённое/задублированное на странице
        Ozon в нескольких полях (см. products-dict-gradation-audit.md,
        разбор "эмблема автомобильная") - кандидат с нулевым
        совпадением в TITLE/SLUG набирал достаточно очков, чтобы
        пройти как уверенное решение (SOURCE=PRODUCTS,
        Уверенность=100%) вместо ухода на ручную проверку.

        Берём ЛУЧШЕЕ совпадение среди всех текстов и начисляем очки
        только один раз - так же, как уже сделано для алиасов."""

        best = None  # (matched_weight, is_similar)

        for text in texts:

            result = self._match_weight(text, phrase, weight)

            if result is None:
                continue

            matched_weight, is_similar = result

            if best is None or matched_weight > best[0]:
                best = (matched_weight, is_similar)

        if best is None:
            return

        matched_weight, is_similar = best

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
        верное).

        Также ослабляем, если фраза - один из вариантов в перечислении
        через запятую/"или" ("подходит для телефона, mp3-плеера или
        планшета" - это описание СОВМЕСТИМОСТИ товара с разными
        устройствами, а не сам товар; раньше такое перечисление в
        длинном маркетинговом описании давало полный вес каждому
        упомянутому устройству)."""

        pos = text.find(phrase)

        if pos <= 0:
            return weight

        preceding = text[:pos].rstrip()
        following = text[pos + len(phrase):].lstrip()

        for prep in self._CONTEXT_PREPOSITIONS:
            if preceding == prep or preceding.endswith(" " + prep):
                return int(weight * 0.25)

        if (
                preceding.endswith(",")
                or preceding.endswith(" или")
                or following.startswith(",")
                or following.startswith("или ")
        ):
            return int(weight * 0.25)

        return weight

    # Падежи, в которых слово почти всегда обозначает "принадлежность
    # чему-то другому" ("спинки автомобильноГО сиденьЯ" - родительный
    # падеж, "деталь ДЛЯ/У сиденья", а не само сиденье), а не сам
    # называемый товар. Именительный (nomn) и винительный (accs, чаще
    # всего - прямое дополнение "купить X"/название в заголовке)
    # сознательно не входят сюда - это как раз обычные падежи для
    # "сам товар назван в тексте".
    _MODIFIER_CASES = ("gent", "datv", "ablt", "loct")

    def _weaken_if_modifier_context_lemma(self, text, phrase_lemmas, weight):
        """Как _weaken_if_modifier_context, но для лемматизированного
        совпадения - в тексте стоит другая словоформа ("газонокосилки"
        вместо "газонокосилка" из словаря), обычный text.find(phrase)
        её не находит вообще, поэтому штраф за предлог-модификатор
        никогда не применялся к этому пути. Ищем слово по лемме и
        проверяем предлог перед НИМ, а не перед точной фразой.

        ДОБАВЛЕНО: реальный случай ложного совпадения без единого
        предлога - "Ручка регулировки спинки автомобильного сиденья"
        (сам товар - РУЧКА, деталь регулировки) лемматизированно
        совпадала с товаром словаря "сиденье автомобильное" (score
        480, CONFIDENCE 100%), потому что и "сиденье", и
        "автомобильное" встречаются в тексте - просто в родительном
        падеже, без всякого предлога-модификатора ("для"/"на"/...).
        Русский родительный падеж без предлога значит то же самое,
        что "для X" - деталь/принадлежность X, а не сам X. Проверяем
        падеж СОВПАВШЕГО слова (через pymorphy3, см.
        cleaner/morphology.py::case) - если он один из "падежей
        принадлежности" (_MODIFIER_CASES), ослабляем вес так же, как
        и для явного предлога. products-dict-gradation-audit.md,
        обновление (11)."""

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

                if word_case(word_clean) in self._MODIFIER_CASES:
                    return int(weight * 0.25)

                if i == 0:
                    return weight

                preceding_raw = words[i - 1]
                preceding = preceding_raw.strip(".,!?;:()\"'«»-").lower()

                if preceding in self._CONTEXT_PREPOSITIONS:
                    return int(weight * 0.25)

                following_raw = words[i + 1] if i + 1 < len(words) else ""
                following = following_raw.strip(".,!?;:()\"'«»-").lower()

                if (
                        preceding_raw.rstrip().endswith(",")
                        or preceding == "или"
                        or following_raw.lstrip().startswith(",")
                        or following == "или"
                ):
                    return int(weight * 0.25)

                return weight

        return weight
    # ==============================================================
    # PENALTIES
    # ==============================================================
    @staticmethod
    def _sum_by_prefix(breakdown, prefix):
        """Сумма всех breakdown-ключей, начинающихся с prefix - то
        есть базовый тип совпадения ВМЕСТЕ с его "_SIMILAR"/"_ALIAS"/
        "_ALIAS_SIMILAR" вариантами (см. Candidate.add в
        resolver/candidate.py и source + ("_SIMILAR" if ... else "")
        в _field_score/_score_aliases выше)."""

        return sum(
            points
            for key, points in breakdown.items()
            if key.startswith(prefix)
        )

    def _apply_penalties(self, candidate, relaxed=False):

        breakdown = candidate.breakdown
        # ДОБАВЛЕНО: раньше здесь стояло breakdown.get("TITLE", 0) -
        # буквальное совпадение с именем товара, БЕЗ учёта TITLE_ALIAS
        # (совпадение по алиасу товара - например, "проходное кольцо"
        # как алиас "кольцо уплотнительное"). Из-за этого кандидат с
        # РЕАЛЬНЫМ, буквальным совпадением алиаса прямо в заголовке
        # карточки (TITLE_ALIAS=300) считался как будто вообще без
        # заголовка (title==0) и получал полный штраф -500 - разбор
        # кейса "Проходное кольцо" (products-dict-gradation-audit.md):
        # даже после добавления алиаса и material_codes кандидат
        # 'кольцо уплотнительное' с TITLE_ALIAS=300+CLEANED_ALIAS=250
        # всё равно проигрывал обычному 'кольцо' из-за этого штрафа.
        # Аналогично для SLUG/DESCRIPTION - используем сумму по
        # префиксу (TITLE/TITLE_SIMILAR/TITLE_ALIAS/
        # TITLE_ALIAS_SIMILAR и т.п.), а не только точное имя ключа.
        title = self._sum_by_prefix(breakdown, "TITLE")
        slug = self._sum_by_prefix(breakdown, "SLUG")
        # "DESC_ALIAS" (не "DESCRIPTION_ALIAS" - см. _score_aliases
        # выше) не подхватывается префиксом "DESCRIPTION", поэтому
        # считаем отдельно и складываем.
        desc = (
            self._sum_by_prefix(breakdown, "DESCRIPTION")
            + self._sum_by_prefix(breakdown, "DESC_ALIAS")
        )
        # SPECS_SIMILAR (нечёткое совпадение характеристики) той же
        # природы, что и SPECS - тоже суммируем по префиксу.
        specs = self._sum_by_prefix(breakdown, "SPECS")
        breadcrumb = self._sum_by_prefix(breakdown, "BREADCRUMB")
        image_desc = self._sum_by_prefix(breakdown, "IMAGE_DESC")

        if title == 0 and slug == 0:
            if image_desc > 0:
                # Описание с картинки запрашивается ИМЕННО когда
                # title/description уже пусты - это ожидаемый, а не
                # тревожный случай. Применяем тот же смягчённый штраф,
                # что и для breadcrumb, а не полный -500.
                candidate.score -= 150
            elif breadcrumb > 0:
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
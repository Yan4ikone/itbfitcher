from resolver.candidate import Candidate
from utils.tokenizer import lemmatized_tokens


class CandidateFinder:

    def __init__(self, repository):

        self.repository = repository

    # ==============================================================
    # PUBLIC
    # ==============================================================

    def find(self, parsed):

        candidates = []

        tokens = parsed.get("tokens", set())

        breadcrumb_tokens = set()

        for crumb in parsed.get("breadcrumbs", []) or []:
            breadcrumb_tokens |= lemmatized_tokens(crumb)

        if not tokens and not breadcrumb_tokens:
            return []

        # ----------------------------------------------------------
        # БЫСТРЫЙ ИНДЕКС
        #
        # Объединяем товары, найденные по токенам заголовка/описания,
        # с товарами, найденные по токенам категории/подкатегории
        # (breadcrumbs с маркетплейса) - иначе товар с мусорным
        # названием, но чёткой категорией ("Мягкие игрушки"), никогда
        # не попадёт в этот список вообще, и _can_match() до него не
        # дойдёт.
        # ----------------------------------------------------------

        products = set(
            self.repository.find_candidate_products(tokens)
        )

        if breadcrumb_tokens:
            products |= self.repository.find_candidate_products(
                breadcrumb_tokens
            )

        # ----------------------------------------------------------
        # FALLBACK
        #
        # Если индекс ничего не нашёл, сохраняем старое поведение:
        # полный перебор.
        #
        # Это важно для безопасности результатов.
        # ----------------------------------------------------------

        if not products:

            products = (
                product
                for product, info
                in self.repository.all()
            )

            for product in products:

                info = self.repository.get(product)

                if not info:
                    continue

                if not self._can_match(
                    product,
                    info,
                    parsed,
                ):
                    continue

                candidates.append(
                    Candidate(
                        product=product,
                        code=str(
                            info.get(
                                "code",
                                ""
                            )
                        ),
                        info=info,
                    )
                )

            return candidates

        # ----------------------------------------------------------
        # ПРОВЕРЯЕМ ТОЛЬКО КАНДИДАТОВ ИЗ ИНДЕКСА
        # ----------------------------------------------------------

        for product in products:

            info = self.repository.get(product)

            if not info:
                continue

            if not self._can_match(
                product,
                info,
                parsed,
            ):
                continue

            candidates.append(
                Candidate(
                    product=product,
                    code=str(
                        info.get(
                            "code",
                            ""
                        )
                    ),
                    info=info,
                )
            )

        return candidates

    # ==============================================================
    # MATCH
    # ==============================================================

    def _can_match(
        self,
        product,
        info,
        parsed,
    ):

        tokens = parsed.get(
            "tokens",
            set(),
        )

        # ----------------------------------------------------------
        # BREADCRUMBS (категория/подкатегория с маркетплейса)
        #
        # Раньше breadcrumbs учитывались только в CandidateScorer при
        # досчёте очков УЖЕ отобранным кандидатам - но не здесь, при
        # первичном отборе. Если название карточки состоит целиком из
        # маркетингового текста без единого пересечения с товаром, а
        # категория чётко говорит "Мягкие игрушки" - товар должен хотя
        # бы ПОПАСТЬ в кандидаты, чтобы его вообще могли оценить.
        # ----------------------------------------------------------

        breadcrumb_tokens = set()

        for crumb in parsed.get("breadcrumbs", []) or []:
            breadcrumb_tokens |= lemmatized_tokens(crumb)

        if breadcrumb_tokens:

            product_tokens_for_breadcrumb = (
                self.repository.product_tokens.get(product)
            )

            if product_tokens_for_breadcrumb is None:
                product_tokens_for_breadcrumb = self._tokens(product)

            if product_tokens_for_breadcrumb & breadcrumb_tokens:
                return True

        # ----------------------------------------------------------
        # PRODUCT TOKENS
        #
        # Используем заранее построенный кэш ProductRepository.
        # ----------------------------------------------------------

        product_tokens = (
            self.repository.product_tokens.get(
                product
            )
        )

        if product_tokens is None:

            product_tokens = self._tokens(
                product
            )

        if product_tokens & tokens:
            return True

        # ----------------------------------------------------------
        # ALIASES
        # ----------------------------------------------------------

        for alias in info.get(
            "aliases",
            []
        ):

            alias_tokens = (
                self.repository.alias_tokens.get(
                    (product, alias)
                )
            )

            if alias_tokens is None:

                alias_tokens = self._tokens(
                    alias
                )

            if alias_tokens & tokens:
                return True

        # ----------------------------------------------------------
        # SCORE WORDS
        # ----------------------------------------------------------

        score_words = info.get(
            "score_words",
            []
        )

        if score_words:

            specs = parsed.get(
                "specs",
                {}
            )

            # Спеки карточки токенизируем один раз
            # для этого кандидата.
            spec_token_sets = []

            for value in specs.values():

                if not value:
                    continue

                spec_token_sets.append(
                    self._tokens(
                        str(value)
                    )
                )

            for word in score_words:

                word_lower = (
                    next(iter(lemmatized_tokens(word)), "")
                )

                if word_lower in tokens:
                    return True

                for spec_tokens in spec_token_sets:

                    if product_tokens & spec_tokens:
                        return True

                    for alias in info.get(
                        "aliases",
                        []
                    ):

                        alias_tokens = (
                            self.repository.alias_tokens.get(
                                (product, alias)
                            )
                        )

                        if alias_tokens is None:

                            alias_tokens = self._tokens(
                                alias
                            )

                        if alias_tokens & spec_tokens:
                            return True

        return False

    # ==============================================================
    # TOKENS
    # ==============================================================

    @staticmethod
    def _tokens(text):

        return lemmatized_tokens(text)
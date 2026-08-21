from resolver.candidate import Candidate


class CandidateFinder:

    def __init__(self, repository):

        self.repository = repository

    # ==============================================================
    # PUBLIC
    # ==============================================================

    def find(self, parsed):

        candidates = []

        tokens = parsed.get("tokens", set())

        if not tokens:
            return []

        # ----------------------------------------------------------
        # БЫСТРЫЙ ИНДЕКС
        # ----------------------------------------------------------

        products = self.repository.find_candidate_products(
            tokens
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
                    str(word)
                    .lower()
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

        return {
            word.lower()
            for word in str(text).split()
            if len(word) > 2
        }
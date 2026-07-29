from resolver.candidate import Candidate


class CandidateFinder:

    def __init__(self, repository):

        self.repository = repository

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def find(self, parsed):

        candidates = []

        tokens = parsed["tokens"]

        if not tokens:
            return []

        for product, info in self.repository.all():

            candidate = Candidate(
                product=product,
                code=str(info.get("code", "")),
                info=info,
            )

            if not self._can_match(
                product,
                info,
                tokens,
            ):
                continue

            candidates.append(candidate)

        return candidates

    # ==========================================================
    # FILTER
    # ==========================================================

    def _can_match(
        self,
        product,
        info,
        tokens,
    ):

        product_tokens = self._tokens(product)

        if product_tokens & tokens:
            return True

        for alias in info.get(
                "aliases",
                [],
        ):

            if self._tokens(alias) & tokens:
                return True

        for word in info.get(
                "score_words",
                [],
        ):

            if word.lower() in tokens:
                return True

        return False

    # ==========================================================
    # TOKENIZE
    # ==========================================================

    def _tokens(self, text):

        return {
            word.lower()
            for word in text.split()
            if len(word) > 2
        }
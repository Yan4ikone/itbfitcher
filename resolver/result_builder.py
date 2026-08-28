from modules.classification_result import ClassificationResult


class ResultBuilder:

    def build(self, winner, candidates):

        result = ClassificationResult()

        if winner is None:
            result.source = "NOT_FOUND"
            return result

        result.product = winner.product
        print(
            "DEBUG PRODUCT TYPE:",
            type(winner.product),
            winner.product
        )
        result.product_scores = candidates
        result.code = winner.code
        result.default_code = winner.code
        result.source = "PRODUCTS"
        result.confidence = min(winner.score, 100)

        # Флаг ручной проверки и причина (NO_CANDIDATES / LOW_CONFIDENCE /
        # AMBIGUOUS / RESOLVED_VIA_EXTRA_DESCRIPTION) должны дойти до
        result.review = winner.review
        result.comment = winner.reason

        if winner.review and candidates:
            result.alternatives = {
                c.code: c.product
                for c in candidates[1:4]
                if c.code
            }

        if winner.material:

            result.material = winner.material

        if winner.material_code:

            result.code = winner.material_code
        result.trace.add(
            "PRODUCT",
            f"{winner.product} ({winner.score})"
        )

        for match in winner.matches:

            result.trace.add(
                match["type"],
                f'+{match["points"]} {match["text"]}',
            )

        return result
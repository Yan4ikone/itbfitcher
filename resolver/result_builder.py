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
        # ------------------------------------------------------
        # Мульти-товарный листинг (см. product_resolver.py::
        # _clear_ambiguous_multi_product_code) - winner.code уже
        # очищен там, если среди кандидатов с максимальным score
        # было несколько РАЗНЫХ кодов. Здесь вместо одного
        # произвольно выбранного названия отдаём куратору названия
        # ВСЕХ настоящих тай-кандидатов сразу ("свеча зажигания /
        # реле / катушка"), и alternatives строим по ним всем (а не
        # только по первым трём после победителя, как в общем
        # случае выше) - победителя как такового здесь нет.
        # ------------------------------------------------------
        if (
            winner.reason == "AMBIGUOUS"
            and not winner.code
            and winner.tied_alternatives
        ):
            # winner.tied_alternatives ({название: код}) снят в
            # product_resolver.py ДО обнуления winner.code - сам
            # winner это тот же объект, что и первый элемент
            # candidates, поэтому пересчитывать коды из candidates
            # здесь уже нельзя (код победителя там тоже пуст).
            result.product = " / ".join(winner.tied_alternatives)
            result.alternatives = {
                code: name
                for name, code in winner.tied_alternatives.items()
            }

        if winner.material:

            result.material = winner.material

        if winner.material_code:

            result.code = winner.material_code
            # Только этот путь означает, что код реально подобран по
            # material_codes конкретного товара - см.
            # engines/decision_engine.py::material_already_resolved.
            result.material_code_resolved = True
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
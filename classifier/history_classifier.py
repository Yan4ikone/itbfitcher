from classifier.similarity import SimilarityClassifier
from classifier.voting import VotingEngine


class HistoryClassifier:

    def __init__(self, knowledge, learning_history):
        self.knowledge = knowledge
        self.similarity = SimilarityClassifier(learning_history)
        self.voting = VotingEngine()

    def apply(self, result, card, resolver):

        history_key = (
                card.cleaned_text
                or card.description
                or card.title
                or ""
        ).lower()

        history = self.knowledge.find_product(history_key)

        if history:
            result.trace.add(
                "HISTORY",
                "Точное совпадение найдено в истории"
            )
        else:
            result.trace.add(
                "HISTORY",
                "Совпадение в истории отсутствует"
            )

        if history:

            history_codes = history["codes"]

            if history_codes:

                if not result.code:

                    code = history_codes.most_common(1)[0][0]

                    resolver.apply(
                        code,
                        "HISTORY",
                        80,
                        f"частота={history_codes[code]}"
                    )

                    result.source = "HISTORY"
                    result.confidence = 80

                    return result

                if result.code in history_codes:

                    result.confidence += min(
                        history_codes[result.code],
                        20
                    )

                    return result

                result.review = True
                return result

        similar, predicted_features, material_code = \
            self.similarity.find(card)

        result.similar_products = len(similar)
        result.features = predicted_features
        result.matched_features = predicted_features

        result.trace.add(
            "SIMILARITY",
            f"Найдено похожих товаров: {len(similar)}"
        )

        if predicted_features:

            result.trace.add(
                "FEATURES",
                f"Определены признаки: {predicted_features}"
            )

        else:

            result.trace.add(
                "FEATURES",
                "Дополнительные признаки не определены"
            )

        if material_code:

            result.trace.add(
                "MATERIAL_HISTORY",
                f"По истории материалов выбран код {material_code}"
            )

        else:

            result.trace.add(
                "MATERIAL_HISTORY",
                "Материал в истории не помог определить код"
            )

        if material_code:

            if not result.code:

                resolver.apply(
                    material_code,
                    "PRODUCT_MATERIAL",
                    95,
                    f"материал={result.material}"
                )

                result.review = True
                return result

            if result.code == material_code:

                result.confidence += 15
                return result

        if not similar:
            return result

        code, amount, counter = self.voting.vote(
            similar,
            result.features or {}
        )

        result.trace.add(
            "VOTING",
            f"Победил код {code} с весом {amount}"
        )

        if amount < 3:
            return result

        if not result.code:

            resolver.apply(
                code,
                "SIMILARITY",
                75,
                f"вес голосования={amount}"
            )

            result.review = True
            return result

        if result.code == code:

            result.confidence += 10
            return result

        result.review = True

        return result
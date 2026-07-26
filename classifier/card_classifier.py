class CardClassifier:

    def __init__(self, knowledge):
        self.knowledge = knowledge

    def apply(self, card, result, resolver):

        history = self.knowledge.find_card(card)

        if not history:
            return None

        result.trace.add(
            "KNOWLEDGE",
            f"Найдена ранее обработанная карточка ({history['code']})"
        )

        resolver.apply(
            history["code"],
            "KNOWLEDGE",
            100,
            "точное совпадение"
        )

        result.product = history.get(
            "product",
            result.product
        )

        result.material = history.get(
            "material",
            ""
        )

        result.confidence = 100

        return result
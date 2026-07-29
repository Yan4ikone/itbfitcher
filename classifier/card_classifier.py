class CardClassifier:

    def __init__(self, knowledge):
        self.knowledge = knowledge

    def apply(self, card, result):

        history = self.knowledge.find_card(card)

        if not history:
            return None

        result.trace.add(
            "KNOWLEDGE",
            f"Найдена ранее обработанная карточка ({history['code']})"
        )
        result.code = history["code"]
        result.source = "CARD_CACHE"
        result.confidence = 100
        if result.source != "PRODUCTS":
            result.product = history.get("product", result.product)
        result.material = history.get("material", "")
        result.confidence = 100

        return result
class CardClassifier:

    def __init__(self, knowledge):
        self.knowledge = knowledge

    def apply(self, card, result):
        print("URL =", repr(card.url))

        if not card.url:
            return None

        history = self.knowledge.find_card(card)
        print("CARD URL:", repr(card.url))
        print("HISTORY:", history)

        if not history:
            return None

        result.trace.add(
            "KNOWLEDGE",
            f"Найдена ранее обработанная карточка ({history.get('code', '')})"
        )
        result.confidence = 100
        if history.get("code"):
            result.code = history["code"]
            result.source = "CARD_CACHE"

        if history.get("product"):
            result.product = history["product"]
        elif history.get("description"):

            result.product = history["description"]
        # ------------------------------------------------------
        # МАТЕРИАЛ
        # ------------------------------------------------------
        if "material" in history:
            result.material = history.get("material", "")
        result.confidence = 100

        return result
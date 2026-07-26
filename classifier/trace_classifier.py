class TraceClassifier:

    def apply(self, card, result):

        result.trace.add("CARD", f"url={card.url}")
        result.trace.add("CARD", f"slug={card.slug}")
        result.trace.add("CARD", f"title={card.title}")
        result.trace.add("CARD", f"description={card.description}")
        result.trace.add("CARD", f"material={card.material}")
        result.trace.add("CARD", f"quantity={card.quantity}")
        result.trace.add("CARD", f"specs={card.specs}")

        result.trace.add(
            "CLASSIFY",
            f"Классификатор: товар={result.product or '-'}, "
            f"код={result.code or '-'}, "
            f"источник={result.source or '-'}"
        )

        result.original_name = card.title

        return result
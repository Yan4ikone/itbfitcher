from engines.knowledge_engine import KnowledgeEngine
from classifier.dropdown_resolver import DropdownResolver
from classifier.history_classifier import HistoryClassifier
from classifier.card_classifier import CardClassifier
from classifier.learning_classifier import LearningClassifier
from classifier.trace_classifier import TraceClassifier

from engines.engine import ResolverEngine
from resolver.excel_name_builder import ExcelNameBuilder
from resolver.special_product_resolver import SpecialProductResolver


class DecisionEngine:

    def __init__(self, learning_history):
        self.learning_history = learning_history
        self.knowledge = KnowledgeEngine()
        self.dropdown = DropdownResolver()
        self.history_classifier = HistoryClassifier(self.knowledge, learning_history)
        self.card_classifier = CardClassifier(self.knowledge)
        self.learning_classifier = LearningClassifier(self.knowledge)
        self.trace_classifier = TraceClassifier()
        self.product_engine = ResolverEngine(self.knowledge)
        self.special_products = SpecialProductResolver()

    def decide(self, card):
        special = self.special_products.resolve(card)

        if special:
            result = self.product_engine.classify(card)

            result.product = special["product"]
            result.dropdown = special["dropdown"]
            result.display_name = special["display_name"]
            result.code = special["code"]
            result.source = special["source"]
            result.confidence = special["confidence"]
            result.review = special["review"]

            result.quantity = getattr(card, "quantity", "")
            result.material = getattr(card, "material", "")

            result.trace.add(
                "SPECIAL_PRODUCT",
                f"Специальное правило: {special['source']}"
            )
            return result

        result = self.product_engine.classify(card)
        result.quantity = getattr(card, "quantity", "")
        result.material = getattr(card, "material", "")
        result_from_card = self.card_classifier.apply(card, result)

        if result_from_card:
            return result_from_card

        result = self.trace_classifier.apply(card, result)
        result = self.history_classifier.apply(result, card)
        result = self.learning_classifier.apply(result)
        builder = ExcelNameBuilder()
        result.dropdown = builder.build(card, result.product)
        result.display_name = result.dropdown
        self.knowledge.card_repository.remember(card, result)
        self.knowledge.card_repository.flush()
        print(self.knowledge.card_repository.file)
        print(self.knowledge.card_repository.data.keys())
        result.trace.add(
            "FINAL",
            f"Итог: код={result.code or '-'}, "
            f"источник={result.source or '-'}, "
            f"уверенность={result.confidence}, "
            f"проверка={result.review}"
        )

        return result
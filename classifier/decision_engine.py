from repositories.knowledge_engine import KnowledgeEngine
from classifier.dropdown_resolver import DropdownResolver
from classifier.history_classifier import HistoryClassifier
from classifier.card_classifier import CardClassifier
from classifier.learning_classifier import LearningClassifier
from classifier.trace_classifier import TraceClassifier

from resolver.engine import ResolverEngine


class DecisionEngine:

    def __init__(self, learning_history):
        print("DECISION INIT")
        self.learning_history = learning_history
        self.knowledge = KnowledgeEngine()
        self.dropdown = DropdownResolver()
        self.history_classifier = HistoryClassifier(self.knowledge, learning_history)
        self.card_classifier = CardClassifier(self.knowledge)
        self.learning_classifier = LearningClassifier(self.knowledge)
        self.trace_classifier = TraceClassifier()
        self.product_engine = ResolverEngine(self.knowledge)

    def decide(self, card):
        print("DECIDE CALLED")
        print("DECISION =", __file__)
        print("DecisionEngine =", __file__)
        result = self.product_engine.classify(card)
        result_from_card = self.card_classifier.apply(card, result)

        if result_from_card:
            return result_from_card

        result = self.trace_classifier.apply(card, result)
        result.dropdown = self.dropdown.resolve(result.product)
        result = self.history_classifier.apply(result, card)
        result = self.learning_classifier.apply(result)
        print("BEFORE REMEMBER")
        self.knowledge.card_repository.remember(card, result)
        result.trace.add(
            "FINAL",
            f"Итог: код={result.code or '-'}, "
            f"источник={result.source or '-'}, "
            f"уверенность={result.confidence}, "
            f"проверка={result.review}"
        )
        return result
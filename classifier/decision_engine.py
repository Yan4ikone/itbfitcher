from modules.knowledge_engine import KnowledgeEngine
from modules.product_engine import classify_product
from modules.code_resolver import CodeResolver
from classifier.dropdown_resolver import DropdownResolver
from classifier.history_classifier import HistoryClassifier
from classifier.card_classifier import CardClassifier
from classifier.learning_classifier import LearningClassifier
from classifier.trace_classifier import TraceClassifier
import inspect

print(inspect.getfile(classify_product))


class DecisionEngine:

    def __init__(self, learning_history):
        self.learning_history = learning_history
        self.knowledge = KnowledgeEngine()
        self.dropdown = DropdownResolver()
        self.history_classifier = HistoryClassifier(self.knowledge, learning_history)
        self.card_classifier = CardClassifier(self.knowledge)
        self.learning_classifier = LearningClassifier(self.knowledge)
        self.trace_classifier = TraceClassifier()

    def decide(self, card):
        print("DecisionEngine =", __file__)
        print("classify_product =", inspect.getfile(classify_product))

        result = classify_product(card, self.knowledge)
        resolver = CodeResolver(result)
        result_from_card = self.card_classifier.apply(card, result, resolver)

        if result_from_card:
            return result_from_card

        result = self.trace_classifier.apply(card, result)
        result.dropdown = self.dropdown.resolve(result.product)
        result = self.history_classifier.apply(result, card, resolver)
        result = self.learning_classifier.apply(result)
        result.trace.add(
            "FINAL",
            f"Итог: код={result.code or '-'}, "
            f"источник={result.source or '-'}, "
            f"уверенность={result.confidence}, "
            f"проверка={result.review}"
        )
        return result
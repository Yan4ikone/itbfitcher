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
        self.dropdown = DropdownResolver(self.knowledge.product_repository)
        self.history_classifier = HistoryClassifier(self.knowledge, learning_history)
        self.card_classifier = CardClassifier(self.knowledge)
        self.learning_classifier = LearningClassifier(self.knowledge)
        self.trace_classifier = TraceClassifier()
        self.product_engine = ResolverEngine(self.knowledge)
        self.special_products = SpecialProductResolver()
        self._decide_count = 0
        self._flush_every = 20

    def decide(self, card, remember=True):

        # ==========================================================
        # 1. SPECIAL PRODUCT
        # ==========================================================
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
            print(
                "[DECISION] SPECIAL:",
                card.url,
                "->",
                result.product,
                result.code,
            )
            return result
        # ==========================================================
        # 2. ОСНОВНАЯ КЛАССИФИКАЦИЯ
        # ==========================================================
        result = self.product_engine.classify(card)
        result.quantity = getattr(card, "quantity", "")
        if not result.material:
            result.material = getattr(card, "material", "")
        # ==========================================================
        # 3. DROPDOWN
        # ==========================================================
        if self.dropdown.resolve(result.product):
            self.dropdown.resolve_code(result, card)
            print(
                "DROPDOWN RESOLVED:",
                result.product,
                "-> код:",
                result.code,
                "источник:",
                result.source,
            )
            result.trace.add(
                "DROPDOWN",
                f"Вариант по материалу/спекам: "
                f"код={result.code}, "
                f"источник={result.source}, "
                f"уверенность={result.confidence}"
            )
        # ==========================================================
        # 4. CARD CACHE
        # ==========================================================
        result_from_card = self.card_classifier.apply(card, result)

        if result_from_card:
            builder = ExcelNameBuilder()
            result_from_card.dropdown = builder.build(
                card,
                result_from_card.product,
            )
            result_from_card.display_name = result_from_card.dropdown

            print(
                "[DECISION] CARD_CACHE:",
                card.url,
                "->",
                result_from_card.product,
                result_from_card.code,
            )
            return result_from_card
        # ==========================================================
        # 5. TRACE
        # ==========================================================
        result = self.trace_classifier.apply(card, result)
        # ==========================================================
        # 6. HISTORY
        # ==========================================================
        result = self.history_classifier.apply(result, card)
        # ==========================================================
        # 7. LEARNING
        # ==========================================================
        result = self.learning_classifier.apply(result)
        # ==========================================================
        # 8. EXCEL NAME
        # ==========================================================
        builder = ExcelNameBuilder()
        result.dropdown = builder.build(card, result.product)
        result.display_name = result.dropdown
        # ==========================================================
        # 9. SAVE CARD
        # ==========================================================
        if remember:

            self.knowledge.card_repository.remember(card, result)
            self._decide_count += 1
            print(
                "[CARD SAVE]",
                card.url,
                "code=",
                result.code,
                "product=",
                result.product,
            )
            print(
                "[CARD COUNT]",
                self._decide_count,
                "/",
                self._flush_every,
            )
            if self._decide_count % self._flush_every == 0:
                print(
                    "[CARD FLUSH]",
                    "count=",
                    self._decide_count,
                )
                self.knowledge.card_repository.flush()
        # ==========================================================
        # 10. FINAL
        # ==========================================================
        result.trace.add(
            "FINAL",
            f"Итог: код={result.code or '-'}, "
            f"источник={result.source or '-'}, "
            f"уверенность={result.confidence}, "
            f"проверка={result.review}"
        )
        return result
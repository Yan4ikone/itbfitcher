from classifier.card_preparation_engine import CardPreparationEngine
from resolver.debugger import ResolverDebugger
from resolver.product_resolver import ProductResolver
from resolver.result_builder import ResultBuilder


class ResolverEngine:

    def __init__(self, knowledge):

        self.knowledge = knowledge
        self.preparation = CardPreparationEngine()
        self.resolver = ProductResolver(knowledge.product_repository)
        self.builder = ResultBuilder()
        self.debugger = ResolverDebugger()

    def classify(self, card):
        card = self.preparation.prepare(card)
        winner, candidates = self.resolver.resolve(card)
        parsed = self.resolver.parser.parse(card)
        self.debugger.print(card, parsed, candidates)
        if winner is None:
            raise RuntimeError("ProductResolver returned None")

        return self.builder.build(winner, candidates)
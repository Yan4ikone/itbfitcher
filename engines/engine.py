from resolver.debugger import ResolverDebugger
from resolver.product_resolver import ProductResolver
from resolver.result_builder import ResultBuilder


class ResolverEngine:

    def __init__(self, knowledge):

        self.knowledge = knowledge
        self.resolver = ProductResolver(knowledge.product_repository)
        self.builder = ResultBuilder()
        self.debugger = ResolverDebugger()

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def classify(self, card):

        winner, candidates = self.resolver.resolve(card)
        parsed = self.resolver.parser.parse(card)
        self.debugger.print(card, parsed, candidates)

        return self.builder.build(winner, candidates)
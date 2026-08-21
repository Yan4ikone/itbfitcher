import time

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
        self.last_parsed = None
        self.last_profile = {}

    def classify(self, card):

        t0 = time.perf_counter()
        card = self.preparation.prepare(card)
        t_prepare = time.perf_counter() - t0

        t0 = time.perf_counter()
        winner, candidates = self.resolver.resolve(card)
        t_resolve = time.perf_counter() - t0

        parsed = self.resolver.last_parsed

        self.debugger.print(card, parsed, candidates)
        self.last_profile = {
            "prepare": t_prepare,
            "resolve": t_resolve,
        }

        if winner is None:
            raise RuntimeError("ProductResolver returned None")

        return self.builder.build(winner, candidates)
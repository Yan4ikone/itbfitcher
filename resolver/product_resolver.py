from resolver.candidate import Candidate
from resolver.product_parser import ProductParser
from resolver.candidate_finder import CandidateFinder
from resolver.candidate_scorer import CandidateScorer
from resolver.material_resolver import MaterialResolver


class ProductResolver:

    def __init__(self, repository):

        self.repository = repository
        self.parser = ProductParser()
        self.finder = CandidateFinder(repository)
        self.scorer = CandidateScorer(repository)
        self.materials = MaterialResolver()
    # ==========================================================
    # PUBLIC
    # ==========================================================
    def resolve(self, card):

        parsed = self.parser.parse(card)
        print()
        print("=" * 80)
        print("PARSED PRODUCT")
        print(parsed["product_name"])
        print("=" * 80)
        print()
        candidates = self.find_candidates(parsed)

        if not candidates:
            winner = Candidate(product="")
            winner.review = True
            winner.reason = "NO_CANDIDATES"

            return winner, []

        winner = candidates[0]

        # 1. Проверяем уверенность

        if winner.score < 70:
            winner.review = True
            winner.reason = "LOW_CONFIDENCE"

            return winner, candidates

        # 2. Проверяем отрыв

        if len(candidates) > 1:

            delta = winner.score - candidates[1].score

            if delta < 15:
                winner.review = True
                winner.reason = "AMBIGUOUS"

                return winner, candidates

        # 3. Материал

        material_code = self.materials.resolve(winner, parsed,)

        if material_code:
            winner.code = material_code
        return winner, candidates
    # ==========================================================
    # CANDIDATES
    # ==========================================================
    def find_candidates(self, parsed):

        candidates = self.finder.find(parsed)

        if not candidates:
            return []

        result = []

        for candidate in candidates:

            candidate = self.scorer.score(candidate, parsed)

            if candidate.score > 0:
                result.append(candidate)

        result.sort(
            key=lambda x: x.score,
            reverse=True,
        )
        return result
    # ==========================================================
    # DEBUG
    # ==========================================================
    def print_candidates(self, candidates):

        print("=" * 70)

        for candidate in candidates[:10]:

            print()
            print(candidate.product)
            print("SCORE :", candidate.score)
            print("CODE  :", candidate.code)

            if candidate.material:
                print("MATERIAL :", candidate.material)

            if candidate.material_code:
                print("MAT CODE :", candidate.material_code)
            print("BREAKDOWN")

            for key, value in sorted(
                    candidate.breakdown.items()
            ):
                print(f"   {key:25} {value}")
            print("MATCHES")

            for item in candidate.matches:
                print(
                    f"   +{item['points']:4} "
                    f"{item['type']:20} "
                    f"{item['text']}"
                )
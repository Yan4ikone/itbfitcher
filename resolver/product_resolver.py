import time

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

        # Последний замер по стадиям - для диагностики, где реально
        # уходит время (parse/find/score/material). Читается вызывающим
        # кодом через resolver.last_timing после resolve().
        self.last_timing = {}

    # ==========================================================
    # PUBLIC
    # ==========================================================
    def resolve(self, card):

        t_start = time.perf_counter()

        parsed = self.parser.parse(card)
        self.last_parsed = parsed

        t_parse = time.perf_counter()

        print()
        print("=" * 80)
        print("PARSED PRODUCT")
        print(parsed["product_name"])
        print("=" * 80)
        print()

        candidates = self.find_candidates(parsed)

        t_after_candidates = time.perf_counter()

        if not candidates:
            winner = Candidate(product="")
            winner.review = True
            winner.reason = "NO_CANDIDATES"

            self._record_timing(
                t_start, t_parse, t_after_candidates, 0,
            )

            return winner, []

        winner = candidates[0]

        # 1. Проверяем уверенность

        if winner.score < 70:
            winner.review = True
            winner.reason = "LOW_CONFIDENCE"

            self._record_timing(
                t_start, t_parse, t_after_candidates,
                len(candidates),
            )

            return winner, candidates

        # 2. Проверяем отрыв

        if len(candidates) > 1:

            delta = winner.score - candidates[1].score

            if delta < 15:
                winner.review = True
                winner.reason = "AMBIGUOUS"

                self._record_timing(
                    t_start, t_parse, t_after_candidates,
                    len(candidates),
                )

                return winner, candidates

        # 3. Материал

        material_code = self.materials.resolve(winner, parsed,)

        t_material = time.perf_counter()

        if material_code:
            winner.code = material_code

        self._record_timing(
            t_start, t_parse, t_after_candidates,
            len(candidates), t_material,
        )

        return winner, candidates

    def _record_timing(
        self,
        t_start,
        t_parse,
        t_after_candidates,
        candidates_count,
        t_material=None,
    ):
        """
        find/score уже записаны в self.last_timing внутри
        find_candidates() - здесь досчитываем parse/material/total.
        """

        find_time = self.last_timing.get("find", 0)
        score_time = self.last_timing.get("score", 0)

        material_time = (
            (t_material - t_after_candidates)
            if t_material is not None else 0
        )
        t_end = t_material if t_material is not None else t_after_candidates

        self.last_timing.update({
            "parse": round(t_parse - t_start, 4),
            "find": round(find_time, 4),
            "score": round(score_time, 4),
            "material": round(material_time, 4),
            "total": round(t_end - t_start, 4),
            "candidates_count": candidates_count,
        })

        print(
            f"[TIMING] parse={self.last_timing['parse']:.3f}s  "
            f"find={self.last_timing['find']:.3f}s  "
            f"score={self.last_timing['score']:.3f}s  "
            f"material={self.last_timing['material']:.3f}s  "
            f"total={self.last_timing['total']:.3f}s  "
            f"candidates={candidates_count}"
        )

    # ==========================================================
    # CANDIDATES
    # ==========================================================
    def find_candidates(self, parsed):

        t0 = time.perf_counter()

        candidates = self.finder.find(parsed)

        t_find = time.perf_counter()

        if not candidates:
            self.last_timing["find"] = t_find - t0
            self.last_timing["score"] = 0
            return []

        result = []

        for candidate in candidates:

            candidate = self.scorer.score(candidate, parsed)

            if candidate.score > 0:
                result.append(candidate)

        t_score = time.perf_counter()

        self.last_timing["find"] = t_find - t0
        self.last_timing["score"] = t_score - t_find

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
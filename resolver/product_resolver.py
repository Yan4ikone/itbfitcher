import time

from resolver.candidate import Candidate
from parser.product_parser import ProductParser
from resolver.candidate_finder import CandidateFinder
from resolver.candidate_scorer import CandidateScorer
from resolver.material_resolver import MaterialResolver
from utils.debug import debug_print
from config import (
    LOW_CONFIDENCE_THRESHOLD,
    AMBIGUOUS_GAP_THRESHOLD,
    DISAMBIGUATION_GAP_THRESHOLD,
    SPECS_BOOST_MULTIPLIER,
)


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
        # Данные считаются ВСЕГДА, печатаются - только
        # если DEBUG=True в config.py.
        self.last_timing = {}

    # ==========================================================
    # PUBLIC
    # ==========================================================
    def resolve(self, card):

        t_start = time.perf_counter()

        parsed = self.parser.parse(card)
        self.last_parsed = parsed

        t_parse = time.perf_counter()

        debug_print()
        debug_print("=" * 80)
        debug_print("PARSED PRODUCT")
        debug_print(parsed["product_name"])
        debug_print("=" * 80)
        debug_print()

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
        low_confidence = winner.score < LOW_CONFIDENCE_THRESHOLD
        # 2. Проверяем отрыв
        ambiguous = False

        if len(candidates) > 1:

            delta = winner.score - candidates[1].score

            if delta < AMBIGUOUS_GAP_THRESHOLD:
                ambiguous = True
        # ------------------------------------------------------
        # Не уверены / отрыв мал -> пробуем "дотянуть" решение
        # усиленным весом характеристик/доп описания, прежде
        # чем окончательно отправлять карточку на ручную проверку
        # ------------------------------------------------------
        if low_confidence or ambiguous:

            resolved = self._disambiguate(candidates, parsed)

            if resolved is not None:
                winner, candidates = resolved
            else:
                winner.review = True
                winner.reason = (
                    "LOW_CONFIDENCE" if low_confidence else "AMBIGUOUS"
                )

                self._record_timing(
                    t_start, t_parse, t_after_candidates,
                    len(candidates),
                )

                return winner, candidates

        # 3. Материал

        material_code = self.materials.resolve(winner, parsed)
        t_material = time.perf_counter()

        if material_code:
            winner.code = material_code

        self._record_timing(
            t_start, t_parse, t_after_candidates,
            len(candidates), t_material,
        )

        return winner, candidates

    # ==========================================================
    # DISAMBIGUATION
    #
    # Повторный скоринг того же набора кандидатов с усиленным
    # весом совпадений по характеристикам/доп описанию
    # Возвращает (winner, candidates) если после усиления решение
    # стало уверенным, иначе None - тогда карточка уходит на
    # ручную проверку.
    # ==========================================================
    def _disambiguate(self, candidates, parsed):

        boosted = []

        for candidate in candidates:

            fresh = Candidate(
                product=candidate.product,
                code=candidate.code,
                info=candidate.info,
            )
            fresh = self.scorer.score(
                fresh,
                parsed,
                specs_weight=150 * SPECS_BOOST_MULTIPLIER,
            )
            if fresh.score > 0:
                boosted.append(fresh)

        if not boosted:
            return None

        boosted.sort(
            key=lambda x: (x.score, bool(x.code)),
            reverse=True,
        )
        winner = boosted[0]

        if winner.score < LOW_CONFIDENCE_THRESHOLD:
            return None

        if len(boosted) > 1:

            delta = winner.score - boosted[1].score

            if delta < DISAMBIGUATION_GAP_THRESHOLD:
                return None

        winner.reason = "RESOLVED_VIA_EXTRA_DESCRIPTION"

        debug_print(
            "[DISAMBIGUATE] Решено доп. описанием -> ",
            winner.product,
            "score=", winner.score,
        )

        return winner, boosted

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
        debug_print(
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
            key=lambda x: (x.score, bool(x.code)),
            reverse=True,
        )
        return result
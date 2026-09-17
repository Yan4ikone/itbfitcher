from dataclasses import dataclass, field


@dataclass
class Candidate:

    product: str
    score: int = 0
    code: str = ""
    material: str = ""
    material_code: str = ""
    matches: list = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)
    source: str = ""
    info: dict = field(default_factory=dict)
    review: bool = False
    reason: str = ""

    # Заполняется в product_resolver.py::_clear_ambiguous_multi_product_code
    # для мульти-товарных листингов (несколько РАЗНЫХ товаров с одинаковым
    # топ-score) - {название: код} всех тай-кандидатов, снятое ДО того, как
    # у winner (он же candidates[0] - тот же объект) обнуляется code. Нужно
    # отдельным полем, а не пересчётом из candidates в result_builder.py,
    # потому что winner - тот же объект, что и первый элемент candidates,
    # и обнуление winner.code иначе стирало бы код и оттуда тоже.
    tied_alternatives: dict = field(default_factory=dict)

    def add(self, reason: str, points: int, text: str = ""):

        self.score += points
        self.matches.append(
            {
                "type": reason,
                "points": points,
                "text": text,
            }
        )
        self.breakdown[reason] = (
            self.breakdown.get(reason, 0)
            + points
        )

    def copy(self):

        return Candidate(
            product=self.product,
            score=self.score,
            code=self.code,
            material=self.material,
            material_code=self.material_code,
            matches=list(self.matches),
            breakdown=dict(self.breakdown),
            source=self.source,
            info=dict(self.info),
            review=self.review,
            reason=self.reason,
            tied_alternatives=dict(self.tied_alternatives),
        )
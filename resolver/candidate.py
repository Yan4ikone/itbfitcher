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
        )
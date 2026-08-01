from dataclasses import dataclass, field


@dataclass
class Candidate:

    # товар из PRODUCTS
    product: str
    # итоговый score
    score: int = 0
    # основной код товара
    code: str = ""
    # материал
    material: str = ""
    # найденный код по материалу
    material_code: str = ""
    # почему начислены баллы
    matches: list = field(default_factory=list)
    # подробная разбивка
    breakdown: dict = field(default_factory=dict)
    # источник совпадения
    source: str = ""
    # дополнительные данные
    info: dict = field(default_factory=dict)

    # ---------------------------------------------------------

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

    # ---------------------------------------------------------

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
        )
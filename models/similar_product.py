from dataclasses import dataclass


@dataclass
class SimilarProduct:
    description: str
    code: str
    score: float
    count: int
    materials: dict
    features: dict
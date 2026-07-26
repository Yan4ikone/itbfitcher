from dataclasses import dataclass, field

from modules.decision_trace import DecisionTrace


@dataclass
class ClassificationResult:

    # ---------- Исходные данные ----------

    original_name: str = ""
    normalized_name: str = ""
    characteristics: str = ""
    candidates: list = field(default_factory=list)

    # ---------- Что нашли ----------

    product: str = ""
    material: str = ""
    code: str = ""
    default_code: str = ""

    # ---------- Информация ----------

    confidence: int = 0
    source: str = ""
    product_scores: list = field(default_factory=list)

    # ---------- Требуется проверка ----------

    review: bool = False
    alternatives: dict = field(default_factory=dict)
    comment: str = ""

    # ---------- История ----------

    history_codes: dict = field(default_factory=dict)

    # ---------- Decision Engine ----------

    matched_features: dict = field(default_factory=dict)
    similar_products: int = 0
    matched_history: int = 0
    trace: DecisionTrace = field(default_factory=DecisionTrace)

    # ---------- Excel ----------
    dropdown: str = ""
    color: str = ""
    decision: str = ""
    curator: str = ""
    matched_by: str = ""
    match_score: int = 0
    reason: str = ""

    # ---------- Dropdown ----------
    dropdown_group: str = ""
    material_group: str = ""

    # ---------- Новый товар --------
    new_product: bool = False
    new_dropdown: bool = False
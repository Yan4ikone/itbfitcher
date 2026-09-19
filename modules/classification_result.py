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

    # ---------- Material ----------
    # True только если код пришёл ИМЕННО из material_codes конкретного
    # товара (см. resolver/result_builder.py). НЕ путать с наличием
    # result.material - тот выставляется даже когда material_codes у
    # товара пуст (см. resolver/material_resolver.py, общий fallback
    # find_known_material_group) и сам по себе не значит, что код уже
    # корректно подобран под материал/признак.
    material_code_resolved: bool = False

    # ---------- Новый товар --------
    new_product: bool = False
    new_dropdown: bool = False

    # ---------- Обоснованность решения ----------
    # True, если у выигравшего кандидата в breakdown есть хотя бы одно
    # совпадение в поле, которое продавец написал именно ПРО ЭТОТ товар
    # (заголовок/URL/текстовое описание товара/описание с картинки - или
    # их алиас-варианты) - см. _DIRECT_TEXT_PREFIXES в
    # resolver/result_builder.py. False означает, что решение держится
    # ИСКЛЮЧИТЕЛЬНО на общих/структурных сигналах (категория Ozon,
    # общий паттерн, характеристики) - такие сигналы могут быть неверно
    # заполнены продавцом (см. products-dict-gradation-audit.md,
    # обновление про "ручку переключения передач", ошибочно
    # классифицированную как "ручной инструмент" по чужой категории
    # продавца). Используется в engines/decision_engine.py, чтобы решить,
    # стоит ли подключать ИИ-распознавание по картинке ДАЖЕ когда код уже
    # найден - не только когда код полностью не определён.
    has_direct_text_support: bool = True
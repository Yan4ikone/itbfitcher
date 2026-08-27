from dataclasses import dataclass, field


@dataclass(frozen=True)
class NewProduct:
    description: str
    code: str
    title: str
    url: str
    material: str = ""
    count: int = 1
    selected: bool = True


@dataclass(frozen=True)
class NewAlias:
    product: str
    alias: str
    selected: bool = True


@dataclass(frozen=True)
class NewMaterialCode:
    product: str
    material: str
    code: str
    selected: bool = True


@dataclass(frozen=True)
class NewDropdownVariant:
    product: str
    code: str
    selected: bool = True


@dataclass(frozen=True)
class NewDropdownCandidate:
    """
    Товар, у которого в products.py ЕЩЁ НЕТ блока "dropdown", но
    в проверенных вручную записях (report.processed_cards) для него
    накопилось несколько РАЗНЫХ кодов, не объяснимых уже известными
    material_codes. Это сигнал "этому товару, возможно, нужен
    dropdown" - в отличие от NewDropdownVariant, который добавляет
    вариант к УЖЕ существующему dropdown.

    codes - кортеж пар (код, сколько раз встретился), отсортированный
    по убыванию частоты. Кортеж, а не dict, чтобы dataclass с
    frozen=True оставался безопасным (дефолтный __hash__ по полям).
    """
    product: str
    codes: tuple
    selected: bool = True


@dataclass(frozen=True)
class NewPattern:
    product: str
    pattern: str
    selected: bool = True


@dataclass
class LearningReport:

    new_products: list[NewProduct] = field(default_factory=list)
    new_aliases: list[NewAlias] = field(default_factory=list)
    new_material_codes: list[NewMaterialCode] = field(default_factory=list)
    new_dropdowns: list = field(default_factory=list)
    new_dropdown_variants: list[NewDropdownVariant] = field(default_factory=list)
    new_dropdown_candidates: list[NewDropdownCandidate] = field(default_factory=list)
    new_patterns: list[NewPattern] = field(default_factory=list)
    processed_cards: list[str] = field(default_factory=list)
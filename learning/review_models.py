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


@dataclass
class LearningReport:

    new_products: list[NewProduct] = field(default_factory=list)
    new_aliases: list[NewAlias] = field(default_factory=list)
    new_material_codes: list[NewMaterialCode] = field(default_factory=list)
    new_dropdowns: list = field(default_factory=list)
    new_dropdown_variants: list[NewDropdownVariant] = field(default_factory=list)
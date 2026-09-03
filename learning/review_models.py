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
    """
    name/match - автозаполняются из карточки, которую куратор
    подтвердил (см. learning.learning_filters.extract_dropdown_keywords),
    чтобы не заполнять их вручную в products.py. Куратор может
    поправить их прямо в окне обучения перед подтверждением.
    """
    product: str
    code: str
    name: str = ""
    match: tuple = ()
    selected: bool = True


@dataclass(frozen=True)
class NewDropdownMatchWords:
    """
    Товар и код УЖЕ есть среди вариантов dropdown, но в новой
    подтверждённой карточке нашлись слова, которых пока нет в
    match этого варианта - предлагаем ДОПОЛНИТЬ (расширить) его,
    а не заводить дубликат варианта с тем же кодом.
    """
    product: str
    code: str
    words: tuple
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

    keywords - кортеж пар (код, кортеж слов-кандидатов в match для
    этого кода) - та же автозаполняемая подсказка, что и у
    NewDropdownVariant, только сразу для всех кодов нового dropdown.
    """
    product: str
    codes: tuple
    keywords: tuple = ()
    selected: bool = True


@dataclass(frozen=True)
class NewPattern:
    product: str
    pattern: str
    selected: bool = True


@dataclass
class NewDictionaryWord:
    """
    Слово/фраза, не найденное НИ В ОДНОМ известном словаре (сейчас -
    MATERIAL_ALIASES, GENDER_ALIASES; список словарей расширяемый,
    см. learning/dictionary_registry.py).

    В отличие от NewMaterialCode (который предлагает "материал X уже
    известен системе, добавить код для ЭТОГО товара") - это подлинно
    НОВОЕ знание: сам факт ни в одном словаре ещё не значится ни для
    какого товара.

    dictionary - словарь, в котором ПРЕДПОЛОЖИТЕЛЬНО не хватает слова
    (куда его искали и не нашли, напр. "material"). Это подсказка по
    умолчанию для диалога в окне обучения, а не окончательное решение.

    target_dictionary/target_group - куда куратор РЕШИЛ добавить слово
    (может отличаться от dictionary, если куратор решит, что слово на
    самом деле относится к другому словарю). Заполняются диалогом в
    learning_window.py, поэтому класс НЕ frozen - в отличие от
    остальных моделей в этом файле, где "selected" - это просто
    флаг вкл/выкл, здесь куратору нужно выбрать ЗНАЧЕНИЕ перед
    подтверждением.
    """
    dictionary: str
    word: str
    product: str
    count: int = 1
    selected: bool = False
    target_dictionary: str = ""
    target_group: str = ""


@dataclass
class LearningReport:

    new_products: list[NewProduct] = field(default_factory=list)
    new_aliases: list[NewAlias] = field(default_factory=list)
    new_material_codes: list[NewMaterialCode] = field(default_factory=list)
    new_dropdowns: list = field(default_factory=list)
    new_dropdown_variants: list[NewDropdownVariant] = field(default_factory=list)
    new_dropdown_match_words: list[NewDropdownMatchWords] = field(default_factory=list)
    new_dropdown_candidates: list[NewDropdownCandidate] = field(default_factory=list)
    new_patterns: list[NewPattern] = field(default_factory=list)
    new_dictionary_words: list[NewDictionaryWord] = field(default_factory=list)
    processed_cards: list[str] = field(default_factory=list)
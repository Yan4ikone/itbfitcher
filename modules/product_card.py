from dataclasses import dataclass, field

@dataclass
class ProductCard:

    url: str = ""
    marketplace: str = ""
    slug: str = ""
    title: str = ""
    raw_title: str = ""
    raw_description: str = ""
    extracted_product: str = ""
    description: str = ""
    raw_text: str = ""
    specs: dict = field(default_factory=dict)
    breadcrumbs: list = field(default_factory=list)
    clean_title: str = ""
    brand: str = ""
    country: str = ""
    clean_description: str = ""
    product_candidates: list = field(default_factory=list)
    material: str = ""
    quantity: str = ""
    package: str = ""
    images: list = field(default_factory=list)
    image_description: str = ""
    cleaned_text: str = ""
    features: dict = field(default_factory=dict)
    parser_log: list = field(default_factory=list)
    normalizer_log: list = field(default_factory=list)
    decision_log: list = field(default_factory=list)
    sections: dict = field(default_factory=dict)
    url_product_name: str = ""
    url_product_id: str = ""
    excel_title: str = ""
    # True - страница оказалась антибот/капча-заглушкой Ozon, а не
    # реальной карточкой товара (см. parser/ozon_html_parser.py -
    # parse_ozon_page_async, поиск "captcha"/"antibot" в сыром HTML).
    # processors/ozon_auto_processor.py проверяет этот флаг СРАЗУ
    # после парсинга и полностью пропускает такую карточку -
    # ни классификация, ни запись в Excel (наименование/код), ни
    # сохранение в card_repository/runtime_cards.json не выполняются.
    # По прямому указанию Яна: "лучше оставлять в таком случае
    # наименование и не трогать" - раньше текст капча-страницы
    # (буквально "Antibot Captcha") подставлялся как обычное
    # наименование товара и уходил в классификацию, а иногда даже
    # получал случайный код с confidence, которого хватало, чтобы
    # НЕ попасть под ручную проверку - и такой "результат" оседал в
    # runtime_cards.json, откуда при повторном запуске того же файла
    # подставлялся уже как будто надёжный (см. classifier/
    # card_classifier.py - там кэш применяется безусловно).
    antibot: bool = False
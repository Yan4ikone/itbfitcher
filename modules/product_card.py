from dataclasses import dataclass, field

@dataclass
class ProductCard:

    url: str = ""
    marketplace: str = ""
    slug: str = ""
    title: str = ""
    description: str = ""
    raw_text: str = ""
    specs: dict = field(default_factory=dict)
    clean_title: str = ""
    clean_description: str = ""
    material: str = ""
    quantity: str = ""
    package: str = ""
    images: list = field(default_factory=list)
    cleaned_text: str = ""
    features: dict = field(default_factory=dict)
    parser_log: list = field(default_factory=list)
    normalizer_log: list = field(default_factory=list)
    decision_log: list = field(default_factory=list)
    sections: dict = field(default_factory=dict)
    url_product_name: str = ""
    url_product_id: str = ""
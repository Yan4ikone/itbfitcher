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
    clean_title: str = ""
    brand: str = ""
    country: str = ""
    clean_description: str = ""
    product_candidates: list = field(default_factory=list)
    material: str = ""
    quantity: str = ""
    volume: str = ""
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
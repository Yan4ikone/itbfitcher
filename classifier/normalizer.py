import re

from cleaner.product_cleaner import clean_text
from cleaner.product_extractor import ProductExtractor


class Normalizer:

    def __init__(self):
        self.extractor = ProductExtractor()

    def normalize(self, text: str) -> str:

        if not text:
            return ""

        cleaned, _, _ = clean_text(text)
        cleaned = cleaned.lower()
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        product = self.extractor.extract(cleaned)
        product = re.sub(r"\s+", " ", product).strip()

        return product


_normalizer = Normalizer()

def normalize_name(text: str) -> str:
    return _normalizer.normalize(text)
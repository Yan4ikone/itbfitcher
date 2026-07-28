import re

from cleaner.product_cleaner import clean_text


def normalize_name(text: str) -> str:

    if not text:
        return ""

    cleaned, _, _ = clean_text(text)
    cleaned = cleaned.lower().strip()
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned
import re
from functools import lru_cache

from dictionaries.all_dictionaries import REMOVE_WORDS


COUNT_PATTERNS = [
    r"\b\d+\s*шт\b",
    r"\b\d+\s*шт\.\b",
    r"\b\d+\s*пара\b",
    r"\b\d+\s*пар\b",
    r"\b\d+\s*пары\b",
    r"\bкомплект\s+из\s+\d+\b",
    r"\bнабор\s+из\s+\d+\b",
    r"\bиз\s+\d+\s*шт\b",
    r"\b\d+\b",
]

_COMPILED_COUNT_PATTERNS = [
    re.compile(pattern, flags=re.IGNORECASE)
    for pattern in COUNT_PATTERNS
]


def clean_dictionary_name(text: str) -> str:

    if not text:
        return ""

    text = text.lower().strip()

    text = text.replace("/", " ")
    text = text.replace("\\", " ")
    text = text.replace(",", " ")
    text = text.replace("(", " ")
    text = text.replace(")", " ")
    text = text.replace("-", " ")

    for pattern in _COMPILED_COUNT_PATTERNS:
        text = pattern.sub(" ", text)

    text = re.sub(r"\s+", " ", text)

    words = []

    for word in text.split():

        if word in REMOVE_WORDS:
            continue

        if word.isdigit():
            continue

        words.append(word)

    return " ".join(words).strip()

@lru_cache(maxsize=8192)
def normalize_dictionary_name(text: str) -> str:

    return clean_dictionary_name(text)
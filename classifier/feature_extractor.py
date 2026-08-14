import re
from dictionaries.all_dictionaries import (MATERIAL_ALIASES, PRODUCT_TYPE_ALIASES, PURPOSE_ALIASES, )

def _find_alias(words, aliases):

    for value, variants in aliases.items():
        for variant in variants:

            variant_words = variant.lower().split()

            if all(word in words for word in variant_words):

                return value
    return None


def extract_features(card):

    words = extract_words(card)
    features = {}
    material = _find_alias(words, MATERIAL_ALIASES)

    if material:
        features["material"] = material

    product_type = _find_alias(words, PRODUCT_TYPE_ALIASES)

    if product_type:
        features["product_type"] = product_type

    purpose = _find_alias(words, PURPOSE_ALIASES)

    if purpose:
        features["purpose"] = purpose

    return features

def extract_words(card):

    words = []

    if card.cleaned_text:
        words.extend(
            re.findall(
                r"[а-яa-z0-9]+",
                card.cleaned_text.lower()
            )
        )
    for value in card.specs.values():
        if value:
            words.extend(
                re.findall(
                    r"[а-яa-z0-9]+",
                    str(value).lower()
                )
            )
    return words
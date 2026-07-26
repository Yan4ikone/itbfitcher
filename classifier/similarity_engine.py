import re
from collections import Counter

from classifier.feature_extractor import extract_features
from dictionaries.all_dictionaries import STOP_WORDS
from config import (FEATURE_MATCH_WEIGHT, MIN_SIMILARITY_SCORE, SIMILARITY_LIMIT,)
from models.similar_product import SimilarProduct


def tokenize(text: str) -> list[str]:

    if not text:
        return []

    words = re.findall(
        r"[а-яa-z0-9]+",
        text.lower()
    )

    return [
        word
        for word in words
        if len(word) > 1 and word not in STOP_WORDS
    ]


def similarity(query_tokens, history_tokens):

    if not query_tokens or not history_tokens:
        return 0

    query_counter = Counter(query_tokens)
    history_counter = Counter(history_tokens)
    score = sum(
        min(query_counter[word], history_counter[word])
        for word in query_counter
        if word in history_counter
    )

    max_words = max(
        len(query_tokens),
        len(history_tokens)
    )

    return round(score / max_words * 100, 2)


def feature_score(query_features, history_features):

    matched = 0

    for key, value in query_features.items():

        if history_features.get(key) == value:
            matched += 1

    return matched * FEATURE_MATCH_WEIGHT


def find_similar_products(
    card,
    learning_history,
    limit=SIMILARITY_LIMIT
):

    query_tokens = tokenize(card.cleaned_text)
    query_features = extract_features(card)

    similar = []

    for item in learning_history.values():

        history_tokens = item.get("tokens", [])
        history_features = item.get("features", {})
        history_codes = item.get("codes", {})
        history_materials = item.get("materials", {})

        score = similarity(
            query_tokens,
            history_tokens
        )

        score += feature_score(
            query_features,
            history_features
        )

        if score < MIN_SIMILARITY_SCORE:
            continue

        for code, count in history_codes.items():
            similar.append(
                SimilarProduct(
                    description=item.get("description", ""),
                    code=code,
                    score=score,
                    count=count,
                    materials=history_materials,
                    features=history_features,
                )
            )

    similar.sort(key=lambda item: (item.score, item.count), reverse=True)

    return similar[:limit]
import re

from dictionaries.all_dictionaries import (
    TRASH_BRANDS,
    TRASH_MARKETING,
    TRASH_MARKETPLACE,
    TRASH_PACKAGE,
    FORBIDDEN_WORDS
)


def clean_text(text: str):

    if not text:
        return "", [], []

    removed = []
    replaced = []

    for pattern, replacement in FORBIDDEN_WORDS.items():

        new_text = re.sub(
            pattern,
            replacement,
            text,
            flags=re.IGNORECASE
        )

        if new_text != text:
            replaced.append(
                f"{pattern} → {replacement}"
            )

        text = new_text

    trash = (
        TRASH_BRANDS
        | TRASH_MARKETING
        | TRASH_MARKETPLACE
        | TRASH_PACKAGE
    )

    result = text

    for word in trash:

        if re.search(
            rf"\b{re.escape(word)}\b",
            result,
            flags=re.IGNORECASE
        ):

            removed.append(word)

            result = re.sub(
                rf"\b{re.escape(word)}\b",
                " ",
                result,
                flags=re.IGNORECASE
            )

    result = re.sub(r"\s+", " ", result)

    return result.strip(), removed, replaced
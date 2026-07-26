import re


BAD_PATTERNS = [

    r"^[a-z0-9_-]{4,12}$",
    r"^[A-Z0-9-]+$",
    r"^[0-9]+$"

]

def is_good_alias(text):

    text = (text or "").strip()

    if len(text) < 5:
        return False

    if len(text.split()) < 2:
        return False

    digits = sum(c.isdigit() for c in text)

    if digits > len(text) * 0.4:
        return False

    for pattern in BAD_PATTERNS:

        if re.fullmatch(pattern, text):
            return False

    return True
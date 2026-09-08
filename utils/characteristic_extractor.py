import re

from dictionaries.all_dictionaries import CHARACTERISTIC_ALIASES


_KNOWN_CHARACTERISTIC_WORDS = {
    canonical: [str(alias).strip().lower() for alias in aliases if str(alias).strip()]
    for canonical, aliases in CHARACTERISTIC_ALIASES.items()
}


def find_known_characteristic(text: str) -> str:
    """Ищет в свободном тексте (заголовок/описание/характеристики) любое
    известное слово-маркер из справочника CHARACTERISTIC_ALIASES
    (электро/ручное/бытовое). Возвращает канонический ключ ("electric"/
    "manual"/"household") под который найденное слово подпадает - то,
    что встречается РАНЬШЕ ВСЕХ по тексту; при совпадении на одной
    позиции выбирает более длинное/специфичное слово.

    Возвращает "", если в тексте нет ни одного известного маркера.
    """

    if not text:
        return ""

    text = str(text).lower()

    best = None  # (start_pos, -length, canonical)

    for canonical, words in _KNOWN_CHARACTERISTIC_WORDS.items():
        for word in words:
            match = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text)
            if match:
                candidate = (match.start(), -len(word), canonical)
                if best is None or candidate < best:
                    best = candidate

    return best[2] if best else ""

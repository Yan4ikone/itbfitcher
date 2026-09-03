import re

from dictionaries.all_dictionaries import GENDER_ALIASES


_KNOWN_GENDER_WORDS = {
    canonical: [str(alias).strip().lower() for alias in aliases if str(alias).strip()]
    for canonical, aliases in GENDER_ALIASES.items()
}


def find_known_gender(text: str) -> str:
    """Ищет в свободном тексте (заголовок/описание/характеристики) любое
    известное слово-маркер пола/возрастной группы из справочника
    GENDER_ALIASES. Возвращает канонический ключ ("male"/"female"/
    "child"), под который найденное слово подпадает - то, что
    встречается РАНЬШЕ ВСЕХ по тексту; при совпадении на одной позиции
    выбирает более длинное/специфичное слово ("для мальчиков" вместо
    гипотетического более короткого совпадения).
    Возвращает "", если в тексте нет ни одного известного маркера -
    это НЕ означает пол "не определён автоматически поэтому берём
    первый вариант", вызывающий код должен трактовать пустую строку
    как "недостаточно сигнала, нужна ручная проверка".
    """

    if not text:
        return ""

    text = str(text).lower()

    best = None  # (start_pos, -length, canonical)

    for canonical, words in _KNOWN_GENDER_WORDS.items():
        for word in words:
            match = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text)
            if match:
                candidate = (match.start(), -len(word), canonical)
                if best is None or candidate < best:
                    best = candidate

    return best[2] if best else ""

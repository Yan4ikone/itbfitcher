import re

from dictionaries.all_dictionaries import PURPOSE_ALIASES


_KNOWN_PURPOSE_WORDS = {
    canonical: [str(alias).strip().lower() for alias in aliases if str(alias).strip()]
    for canonical, aliases in PURPOSE_ALIASES.items()
}


def find_known_purpose(text: str) -> str:
    """Ищет в свободном тексте (заголовок/описание/характеристики) любое
    известное слово-маркер "назначения" товара из справочника
    PURPOSE_ALIASES ("для автомобиля"/"для животных"/"вода"/"магнит" и
    т.п.). Возвращает канонический ключ (по-русски, ровно как он
    записан в group у dropdown-варианта - "animal"/"automobile"/
    "water"/... - см. PURPOSE_ALIASES), под который найденное слово
    подпадает - то, что встречается РАНЬШЕ ВСЕХ по тексту; при
    совпадении на одной позиции выбирает более длинное/специфичное
    слово (аналогично find_known_gender/find_known_characteristic).

    Возвращает "", если в тексте нет ни одного известного маркера -
    это НЕ означает "назначение неизвестно, берём первый вариант",
    вызывающий код должен трактовать пустую строку как "недостаточно
    сигнала, нужна ручная проверка".
    """

    if not text:
        return ""

    text = str(text).lower()

    best = None  # (start_pos, -length, canonical)

    for canonical, words in _KNOWN_PURPOSE_WORDS.items():
        for word in words:
            match = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text)
            if match:
                candidate = (match.start(), -len(word), canonical)
                if best is None or candidate < best:
                    best = candidate

    return best[2] if best else ""

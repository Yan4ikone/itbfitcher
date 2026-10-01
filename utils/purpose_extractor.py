import re

from dictionaries.all_dictionaries import PURPOSE_ALIASES
from utils.groups import canon


_KNOWN_PURPOSE_WORDS = {
    canon(canonical): [str(alias).strip().lower() for alias in aliases if str(alias).strip()]
    for canonical, aliases in PURPOSE_ALIASES.items()
}


def find_known_purpose(text: str, allowed=None) -> str:
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

    # allowed - ограничить поиск ключами, которые реально есть у товара
    # среди вариантов (2026-09-29): иначе широкий ключ вроде "sport" или
    # "carnival", встретившись в тексте раньше, "занимал" место и ось
    # вообще не находила нужный вариант ("bicycle" и т.п.).
    if allowed is not None:
        allowed = {canon(a) for a in allowed}

    for canonical, words in _KNOWN_PURPOSE_WORDS.items():

        if allowed is not None and canonical not in allowed:
            continue

        for word in words:
            match = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text)
            if match:
                candidate = (match.start(), -len(word), canonical)
                if best is None or candidate < best:
                    best = candidate

    return best[2] if best else ""

"""
Единый источник токенизации с лемматизацией.

"""

from cleaner.morphology import Morphology

# Один экземпляр на процесс - MorphAnalyzer дорого инициализировать,
# а Morphology.normal() уже кэширует результаты по словам (lru_cache).
_morphology = Morphology()

# Знаки препинания, приклеивающиеся к слову без пробела в обычном
# тексте ("Велокамера, диаметр..." / "товар." / "цвет:красный").
# из-за чего лемматизация не находила соответствие товару/слову без
# запятой - это ломало сопоставление по лемме ВЕЗДЕ, где совпадение
# оказывалось рядом со знаком препинания, а не только в конце фразы.
_PUNCTUATION = ".,!?;:()\"'«»-–—"


def lemmatized_tokens(text) -> set:
    """Токены текста, приведённые к нормальной форме (лемме).
    Слова короче 3 символов отбрасываются (предлоги, союзы) - тот же
    порог, что был в исходных версиях токенизации."""

    if not text:
        return set()

    words = [
        word.strip(_PUNCTUATION)
        for word in str(text).lower().split()
    ]

    words = [word for word in words if len(word) > 2]

    return {_morphology.normal(word) for word in words}


def word_case(word) -> str:
    """Падеж отдельного слова ('nomn', 'gent', ...) - обёртка над
    общим экземпляром Morphology, см. cleaner/morphology.py::case().
    Используется resolver/candidate_scorer.py, чтобы отличить "само
    название товара" (именительный падеж) от слова, упомянутого лишь
    как принадлежность/деталь чего-то другого (родительный падеж и
    т.п.)."""

    if not word:
        return ""

    word = str(word).strip(_PUNCTUATION)

    if not word:
        return ""

    return _morphology.case(word)

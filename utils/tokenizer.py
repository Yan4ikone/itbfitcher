"""
Единый источник токенизации с лемматизацией.

"""

from cleaner.morphology import Morphology

# Один экземпляр на процесс - MorphAnalyzer дорого инициализировать,
# а Morphology.normal() уже кэширует результаты по словам (lru_cache).
_morphology = Morphology()


def lemmatized_tokens(text) -> set:
    """Токены текста, приведённые к нормальной форме (лемме).
    Слова короче 3 символов отбрасываются (предлоги, союзы) - тот же
    порог, что был в исходных версиях токенизации."""

    if not text:
        return set()

    words = [
        word
        for word in str(text).lower().split()
        if len(word) > 2
    ]

    return {_morphology.normal(word) for word in words}

import re

from dictionaries.all_dictionaries import (
    IGNORED_ALIAS_WORDS,
    TRASH_MARKETING,
    TRASH_MARKETPLACE,
    TRASH_PACKAGE,
)
from learning.name_normalizer import normalize_dictionary_name

# ==================================================================
# ИЗВЛЕЧЕНИЕ ИСПРАВЛЕННЫХ КУРАТОРОМ ЗНАЧЕНИЙ
#
# Единый источник "что куратор реально исправил" для manual-записи
# (manual_learning.json["manual"][normalized_url], её туда кладёт
# ManualTeacher.learn_result_file() из RESULT-файла).
#
# Раньше эта логика была ТОЛЬКО внутри LearningAnalyzer
# (_get_description/_get_code) - когда понадобилось то же самое в
# LearningRuntime.mark_learning_processed() (при архивации карточки
# в лёгкую базу знаний), функцию не переиспользовали, а взяли данные
# из ДРУГОГО источника - storage/runtime_cards.json, то есть из
# результата ПЕРВОНАЧАЛЬНОЙ автоклассификации, а не из ручной правки.
# В базу знаний уходило неисправленное значение. Теперь оба места
# берут исправленное значение отсюда.
# ==================================================================

def extract_manual_description(manual: dict) -> str:

    raw_description = str(manual.get("description", "")).strip()

    if not raw_description:
        return ""

    return (
        normalize_dictionary_name(raw_description)
        .lower()
        .strip()
    )


def extract_manual_code(manual: dict) -> str:

    code = str(manual.get("code", "")).strip()

    if not code:
        return ""

    if code in ("0", "nan", "none"):
        return ""

    return code


# Единый набор "мусорных" слов для алиасов. Раньше AliasBuilder
# (cleaner/alias_builder.py) чистил по всем четырём спискам, а
# is_valid_alias() - только по IGNORED_ALIAS_WORDS. Из-за этого
# алиасы, добавленные через LearningAnalyzer._add_alias() (путь
# "товар найден через ProductMatcher"), проходили без очистки от
# маркетингового/маркетплейсного мусора - в products.py попадали
# строки вроде "футболка акции распродажа скидки российский".
_TRASH_WORDS = (
    IGNORED_ALIAS_WORDS
    | TRASH_MARKETING
    | TRASH_MARKETPLACE
    | TRASH_PACKAGE
)

# Слова-маркеры маркетингового мусора, которые обычно СОСЕДСТВУЮТ
# с полезными словами внутри одной фразы ("футболка акции скидки") -
# их одних в TRASH_MARKETING может не хватать, т.к. alias отбраковывается
# только если ВСЕ слова мусорные. Если хотя бы одно из этих слов есть
# во фразе - алиас почти наверняка результат склейки заголовка с
# маркетинговым хвостом, а не осмысленный синоним товара.
_STRONG_TRASH_MARKERS = {
    "акции", "акция", "распродажа", "скидки", "скидка",
    "рублей", "рубля", "товары", "официально", "рекомендовано",
    "тотальная",
}


def is_valid_alias(alias, product_name=""):

    alias = (alias or "").strip().lower()

    if not alias:
        return False

    # Убираем лишние пробелы
    alias = re.sub(r"\s+", " ", alias)

    # Один из заведомо бесполезных вариантов
    if alias in _TRASH_WORDS:
        return False

    words = alias.split()

    # Если alias состоит из нескольких слов, проверяем,
    # не является ли он просто набором служебных/мусорных слов.
    if words and all(word in _TRASH_WORDS for word in words):
        return False

    # Явный маркетинговый мусор внутри фразы (см. комментарий выше).
    if any(word in _STRONG_TRASH_MARKERS for word in words):
        return False

    # ------------------------------------------------------
    # ПОДМНОЖЕСТВО / НАДМНОЖЕСТВО НАЗВАНИЯ ТОВАРА
    #   товар = "маска косметическая"
    #   "маска" - подмножество (минус слово) - НЕ алиас
    #   "маска косметическая очищение всех типов кожи" -
    #       надмножество (название + хвост) - НЕ алиас
    #   "маска для лица" - другой состав слов - алиас, ок
    # ------------------------------------------------------
    if product_name:

        product_normalized = re.sub(
            r"\s+", " ", (product_name or "").strip().lower()
        )
        product_words = set(product_normalized.split())
        alias_words = set(words)

        if product_words and alias_words:

            if alias_words == product_words:
                return False

            if alias_words < product_words:
                # алиас - строгое подмножество названия
                # (название минус одно или несколько слов)
                return False

            if product_words < alias_words:
                # алиас - строгое надмножество названия
                # (название плюс хвост)
                return False

    return True


def normalize_material(material):
    """
    Приводит материал к одному основному значению.

    Примеры:

        100% полиэстер
            -> полиэстер

        вискоза 67%, полиэстер 33%
            -> вискоза

        70% хлопок 25% полиэстер 5% эластан
            -> хлопок

        металл, пластик, дерево
            -> металл

        металл
            -> металл
    """
    material = (material or "").strip().lower()

    if not material:
        return ""

    material = re.sub(r"\s+", " ", material)
    # --------------------------------------------------
    # Сначала ищем материалы с процентами
    # --------------------------------------------------
    percentage_matches = re.findall(
        r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;]+)",
        material,
    )

    if percentage_matches:

        parsed = []

        for percent, name in percentage_matches:
            try:
                value = float(
                    percent.replace(",", ".")
                )
            except ValueError:
                continue

            name = name.strip()

            # Убираем возможные проценты/лишние пробелы
            name = re.sub(
                r"\s+",
                " ",
                name,
            )
            if name:
                parsed.append(
                    (
                        value,
                        name,
                    )
                )
        if parsed:

            # Берём материал с максимальным процентом.
            # При равенстве сохраняется первый.
            parsed.sort(
                key=lambda x: x[0],
                reverse=True,
            )
            percent, name = parsed[0]

            return name.strip()

    # --------------------------------------------------
    # Если процентов нет — берём первый материал
    # --------------------------------------------------

    # Разделители:
    # "металл, пластик"
    # "металл; пластик"
    # "металл / пластик"
    parts = re.split(
        r"\s*[,;/]\s*",
        material,
    )

    if parts:

        first = parts[0].strip()

        if first:
            return first
    return material
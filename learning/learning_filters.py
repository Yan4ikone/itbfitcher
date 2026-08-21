import re

from dictionaries.all_dictionaries import IGNORED_ALIAS_WORDS


def is_valid_alias(alias, product_name=""):

    alias = (alias or "").strip().lower()

    if not alias:
        return False

    # Убираем лишние пробелы
    alias = re.sub(r"\s+", " ", alias)

    # Один из заведомо бесполезных вариантов
    if alias in IGNORED_ALIAS_WORDS:
        return False

    # Если alias состоит из нескольких слов,
    # проверяем, не является ли он просто набором
    # служебных слов.
    words = alias.split()

    if words and all(
        word in IGNORED_ALIAS_WORDS
        for word in words
    ):
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
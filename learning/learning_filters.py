import re

from dictionaries.all_dictionaries import (
    IGNORED_ALIAS_WORDS,
    MATERIAL_ALIASES,
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


# ==================================================================
# ЧИСТКА МАТЕРИАЛА ("хлопок/синтетика", а не "нейлон, размер 42" или
# "высокопрочный экологичный нейлон")
#
# Отдельный набор мусорных слов - специально НЕ используем
# TRASH_MARKETING/_TRASH_WORDS, т.к. там есть легитимные слова
# материалов ("хлопок", "кожа" и т.п. могут случайно попасть в
# маркетинговый мусор для алиасов, но это не мусор для материала).
# ==================================================================
_MATERIAL_JUNK_WORDS = {
    "размер", "размера", "размеры", "размерный",
    "высокопрочный", "высокопрочная", "высокопрочное", "высокопрочные",
    "износостойкий", "износостойкая", "износостойкое", "износостойкие",
    "экологичный", "экологичная", "экологичное", "экологичные", "эко",
    "прочный", "прочная", "прочное", "прочные",
    "качественный", "качественная", "качественное", "качественные",
    "плотный", "плотная", "плотное", "плотные",
    "мягкий", "мягкая", "мягкое", "мягкие",
    "практичный", "практичная", "практичное",
    "удобный", "удобная", "удобное",
    "стильный", "стильная", "стильное",
    "современный", "современная", "современное",
    "многослойный", "многослойная", "многослойное",
    "дышащий", "дышащая", "дышащее",
    "водоотталкивающий", "водоотталкивающая", "водоотталкивающее",
    "гипоаллергенный", "гипоаллергенная",
    "премиум", "люкс", "класса",
    "прочего", "прочие", "др", "другое",
}

# Плоский список известных названий материалов (алиасы из
# MATERIAL_ALIASES, а не канонические группы) - используется, чтобы
# при наличии нескольких слов в фразе выбрать именно материал, а не
# случайно оставшееся прилагательное.
_KNOWN_MATERIAL_WORDS = sorted(
    {
        alias.lower()
        for aliases in MATERIAL_ALIASES.values()
        for alias in aliases
    },
    key=len,
    reverse=True,
)


def _clean_material_phrase(phrase: str) -> str:
    """Убирает числа (размеры) и мусорные прилагательные из фразы
    материала, оставляя только сами названия материалов."""

    phrase = re.sub(r"\d+", " ", phrase)
    words = [
        word
        for word in phrase.split()
        if word not in _MATERIAL_JUNK_WORDS
    ]
    return re.sub(r"\s+", " ", " ".join(words)).strip(" -")


def _pick_known_material(phrase: str) -> str:
    """Если во фразе есть слово/словосочетание из справочника известных
    материалов - возвращает то, что встречается РАНЬШЕ ВСЕХ по тексту
    (при нескольких материалах без % берём первый упомянутый - как и
    просили). При совпадении на одной и той же позиции выбираем более
    длинное/специфичное совпадение ('искусственная кожа' вместо
    'кожа')."""

    best = None  # (start_pos, -length, word)

    for known in _KNOWN_MATERIAL_WORDS:
        match = re.search(rf"(?<!\w){re.escape(known)}(?!\w)", phrase)
        if match:
            candidate = (match.start(), -len(known), known)
            if best is None or candidate < best:
                best = candidate

    return best[2] if best else ""


# ==================================================================
# КЛЮЧЕВЫЕ СЛОВА ДЛЯ DROPDOWN-ВАРИАНТОВ ("ЗОНТИЧНЫЕ" КАТЕГОРИИ)
#
# Для товаров вроде "аксессуар для пылесоса"/"аксессуар для рыбалки" -
# у которых внутри одного словарного описания несколько РАЗНЫХ по
# сути предметов (см. resolver/dropdown_axis_resolver.py::
# ScoredKeywordAxisResolver) - куратору раньше приходилось вручную
# писать name/match для каждого нового варианта в products.py.
# Эта функция достаёт кандидатов в match автоматически из карточки,
# которую куратор только что подтвердил/исправил.
# ==================================================================

# Кандидат в match должен выглядеть как настоящее слово - только
# буквы (кириллица/латиница) и внутренние дефисы. Отсеивает мусор
# вида артикулов/hex-кодов/размеров, которые иногда пролезают в
# характеристики как "0x17.0x24" - такое в словарь синонимов не
# нужно вообще, никакого потенциала точности от него нет.
_WORD_SHAPE_PATTERN = re.compile(r"^[а-яёa-z]+(?:-[а-яёa-z]+)?$")


def extract_dropdown_keywords(card, description, product_name, max_keywords=3):
    """Значимые слова-кандидаты в match конкретного dropdown-варианта.

    Намеренно исключает слова самого наименования товара-"зонтика"
    (product_name) - иначе ВСЕ варианты получили бы одно и то же
    общее слово ("пылесос") вместо того, что их отличает
    ("фильтр"/"щетка"/"мешок").
    """

    title = str((card or {}).get("title", "") or "")
    specs = (card or {}).get("specs", {}) or {}
    specs_text = " ".join(str(v) for v in specs.values())

    text = " ".join(filter(None, [title, specs_text, description or ""]))
    text = normalize_dictionary_name(text).lower()

    product_words = {
        word
        for word in str(product_name or "").lower().split()
        if word
    }

    # Слова бренда (card.brand) - не годятся в match: иначе вариант
    # "Фильтр для пылесоса" привязался бы только к одному бренду
    # ("xiaomi"), а не к слову "фильтр".
    brand_words = {
        word
        for word in str((card or {}).get("brand", "") or "").lower().split()
        if word
    }

    excluded_words = product_words | brand_words

    words = []
    seen = set()

    for word in text.split():

        word = word.strip()

        if len(word) < 3:
            continue
        if not _WORD_SHAPE_PATTERN.match(word):
            continue
        if word in _TRASH_WORDS:
            continue
        if word in excluded_words:
            continue
        if word in seen:
            continue

        seen.add(word)
        words.append(word)

        if len(words) >= max_keywords:
            break

    return tuple(words)


def normalize_material(material):
    """
    Приводит материал к одному основному, ЧИСТОМУ значению - без
    процентов, без двойных наименований, без мусорных прилагательных
    и размеров.

    Примеры:

        100% полиэстер
            -> полиэстер

        вискоза 67%, полиэстер 33%
            -> вискоза

        70% хлопок 25% полиэстер 5% эластан
            -> хлопок

        нейлон, размер 42
            -> нейлон

        высокопрочный экологичный нейлон
            -> нейлон

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
    # Сначала ищем материалы с процентами - в любом порядке:
    # "70% хлопок" И "хлопок 70%"
    _WORD = r"[а-яёa-z]+(?:\s+[а-яёa-z]+)?"
    percentage_matches = []
    for m in re.finditer(
        rf"(?:(?P<word1>{_WORD})\s+)?"
        rf"(?P<percent>\d+(?:[.,]\d+)?)\s*%\s*"
        rf"(?P<word2>{_WORD})?",
        material,
    ):
        try:
            value = float(m.group("percent").replace(",", "."))
        except ValueError:
            continue
        name = (m.group("word1") or m.group("word2") or "").strip()
        if name:
            percentage_matches.append((value, name))

    if percentage_matches:

        # Берём материал с максимальным процентом.
        # При равенстве сохраняется первый.
        percentage_matches.sort(
            key=lambda x: x[0],
            reverse=True,
        )
        percent, name = percentage_matches[0]

        name = _clean_material_phrase(name)
        # Нет чёткого попадания в справочник материалов - НЕ угадываем
        return _pick_known_material(name)

    # --------------------------------------------------
    # Если процентов нет — ищем известный материал во всей фразе
    # (так "высокопрочный экологичный нейлон" даёт "нейлон", а не
    # "высокопрочный")
    # --------------------------------------------------
    cleaned_full = _clean_material_phrase(material)
    known = _pick_known_material(cleaned_full)

    # Если известного материала во фразе нет вообще - возвращаем "",
    return known
from urllib.parse import urlparse, unquote
import re

from modules.product_card import ProductCard
from utils.quantity_extractor import (
    extract_quantity,
    is_component_count_key,
    is_heterogeneous_kit,
    strip_heterogeneous_kit_segments,
)
from utils.material_extractor import extract_material, is_excluded_material_key


FIELDS = [
    "Тип",
    "Тип товара",
    "Назначение",
    "Особенности",
    "Комплектация",
    "Материал",
    "Форма",
    "Конструкция"
]

def extract_slug(url):

    path = unquote(urlparse(url).path)
    m = re.search(r"/product/(.+?)-\d+/?$", path)

    if not m:
        return ""

    slug = m.group(1)
    slug = slug.replace("-", " ")
    slug = re.sub(r"\s+", " ", slug)

    return slug.strip().lower()

def build_from_excel(description, characteristics="", normalized=""):
    card = ProductCard()
    card.title = description
    card.description = description
    card.cleaned_text = normalized or description

    if characteristics:
        card.specs["Характеристики"] = characteristics

    text = " ".join(filter(None, [description, characteristics]))

    quantity = extract_quantity(text)

    if quantity:
        card.quantity = quantity
    material = extract_material(text)

    if material:
        card.material = material
        card.specs.setdefault("Материал", material)

    return card

def build_product_card(url, parsed, raw_text):

    card = ProductCard()
    card.url = url
    card.slug = extract_slug(url)
    card.url_product_name = card.slug
    card.raw_text = raw_text
    card.title = parsed.get("title", "")
    card.description = parsed.get("description", "")
    card.specs = parsed.get("specs", {})
    card.breadcrumbs = parsed.get("breadcrumbs", [])
    card.images = parsed.get("images", [])
    # ДОБАВЛЕНО: nm_id товара WB (см. parser/wb_parser.py - там же
    # объяснение, зачем). Для Ozon это поле парсером не заполняется
    # вообще (там card.images уже содержит прямые ссылки на фото),
    # так что для Ozon-карточек здесь всегда останется "".
    card.url_product_id = str(parsed.get("url_product_id") or "")
    card.antibot = bool(parsed.get("antibot", False))

    if card.antibot:
        # Антибот/капча Ozon (см. parser/ozon_html_parser.py -
        # parse_ozon_page_async) - дальше по коду НИЧЕГО из этой
        # карточки использовать нельзя (title/description там уже
        # пустые нарочно), просто возвращаем как есть. Обработка
        # (пропуск классификации/записи в Excel/кэша) - на уровне
        # processors/ozon_auto_processor.py, который проверяет
        # card.antibot сразу после парсинга.
        return card

    if not card.title:
        card.title = card.slug

    if not card.cleaned_text:
        if not card.cleaned_text:
            card.cleaned_text = (
                    card.title
                    or card.slug
                    or card.description
            )

    if not card.description or card.description == "Распродажа":
        card.description = card.slug

    # Материал ВЕРХА/основной части (напр. "Материал", "Материал
    # верха", "Состав") - в приоритете над обычным первым найденным
    # спеком, см. пояснение в блоке MATERIAL ниже. material_excluded_
    # value - слабый сигнал "последней надежды" (материал подошвы/
    # подкладки/т.п.) - используется, ТОЛЬКО если вообще ничего
    # больше не нашлось (лучше слабый сигнал, чем никакого).
    material_value = ""
    material_primary_value = ""
    material_excluded_value = ""

    for key, value in card.specs.items():

        key_l = str(key or "").strip().lower()
        value_str = str(value or "").strip()

        if not value_str:
            continue
        # ======================================================
        # MATERIAL
        #
        # У обуви/сумок и т.п. в характеристиках Ozon часто ЕСТЬ
        # несколько разных полей "Материал ..." одновременно -
        # материал ОСНОВНОЙ части (просто "Материал", "Материал
        # верха") и материал ВСПОМОГАТЕЛЬНОЙ части (подошва,
        # подкладка, стелька, утеплитель, фурнитура, молния, шнурки).
        # Раньше здесь брался ПЕРВЫЙ попавшийся ключ, содержащий
        # "материал"/"состав", в порядке, в котором Ozon отдаёт
        # характеристики - а этот порядок никак не гарантирует, что
        # основной материал идёт раньше вспомогательного. На практике
        # ловилось "Материал подошвы обуви: Каучук" (сама подошва) как
        # card.material ДО того, как встречался настоящий "Материал:
        # Натуральная кожа" - товар с реальной кожаной верхней частью
        # уходил в DROPDOWN_UNRESOLVED, потому что резина не совпадает
        # ни с одним dropdown-вариантом ("кожа"/"текстиль").
        #
        # Используем тот же фильтр is_excluded_material_key(), что уже
        # применяется в resolver/material_resolver.py для той же цели -
        # единый источник, не дублируем список слов-исключений. Внутри
        # оставшихся (не вспомогательных) ключей отдельно запоминаем
        # "первичное" совпадение (сам "материал" без уточнения, или
        # явно "материал верха") - оно приоритетнее любого другого
        # немаркированного as-is совпадения ("материал", "состав").
        # Вспомогательный ключ (подошва/подкладка/...) тоже
        # запоминаем отдельно (material_excluded_value) - НЕ как
        # обычный кандидат, а как самый слабый fallback на случай,
        # если у товара вообще нет никакого другого материала нигде.
        # ======================================================
        if "материал" in key_l or "состав" in key_l:

            if is_excluded_material_key(key_l):
                if not material_excluded_value:
                    material_excluded_value = value_str
                continue

            if not material_value:
                material_value = value_str

            is_primary = "верх" in key_l or key_l in ("материал", "состав")

            if is_primary and not material_primary_value:
                material_primary_value = value_str
        # ======================================================
        # QUANTITY
        # ======================================================
        if (
                "количество" in key_l
                or "кол-во" in key_l
                or "кол во" in key_l
                or "в упаковке" in key_l
                or "комплект" in key_l
                or "набор" in key_l
        ):
            # "Комплектация"/"Состав набора" - это ПЕРЕЧЕНЬ того, что
            # лежит в наборе (пылесос, насадка-щётка, шланг), а не
            # количество экземпляров товара. Раньше "комплект" in key_l
            # ловил и "Комплектация" тоже, и если в её значении
            # встречалось "2 шт"/"2 предмета" (сумма РАЗНЫХ компонентов),
            # это ошибочно становилось количеством товара - "пылесос
            # 2 шт" вместо "пылесос (в комплекте с щёткой)".
            is_composition_key = (
                "комплектация" in key_l
                or "состав набора" in key_l
                or "состав комплекта" in key_l
            )

            if is_composition_key and is_heterogeneous_kit(value_str):
                quantity = ""
            else:
                quantity = extract_quantity(value_str)

            # Частый случай на Ozon: единица уже в НАЗВАНИИ поля
            # ("Количество в упаковке, шт"), а само значение -
            # просто голое число ("5"). Тогда unit берём из key.
            #
            # НО: "Количество секций: 3" (шкаф из 3 секций, а не 3
            # шкафа), "Количество деталей: 1056" (конструктор из 1056
            # деталей, а не 1056 фигурок) - здесь ключ считает
            # КОМПОНЕНТЫ/части самого товара, а не число экземпляров
            # товара в упаковке. is_component_count_key() - тот же
            # список слов-исключений, что уже используется в
            # extract_quantity() для аналогичного случая в свободном
            # тексте (см. _NOT_PRODUCT_UNIT в quantity_extractor.py).
            if (
                    not quantity
                    and value_str.isdigit()
                    and not is_composition_key
                    and not is_component_count_key(key_l)
            ):

                number = int(value_str)

                if number >= 2:

                    if "компл" in key_l:
                        unit = "комплект"
                    elif "набор" in key_l:
                        unit = "набор"
                    elif "пар" in key_l:
                        unit = "пар"
                    else:
                        unit = "шт"

                    quantity = f"{number} {unit}"

            if quantity:
                card.quantity = quantity
        # ======================================================
        # VOLUME
        # ======================================================
        if (
                "объем" in key_l
                or "объём" in key_l
        ):
            volume = _extract_volume(value_str)

            if volume:
                card.volume = volume
        # ======================================================
        # COUNTRY
        # ======================================================
        if "страна" in key_l:
            if not card.country:
                card.country = value_str
        # ======================================================
        # BRAND
        # ======================================================
        if "бренд" in key_l:
            if not card.brand:
                card.brand = value_str

    # "Первичный" материал (просто "Материал"/"Состав", или явно
    # "Материал верха") - в приоритете; если такого ключа не было
    # вообще, берём любой другой не-вспомогательный "материал"-ключ
    # (material_value); и только если ВООБЩЕ ничего, кроме материала
    # вспомогательной части (подошва/подкладка/...), не нашлось -
    # используем его как самый слабый сигнал (material_excluded_value),
    # лучше приблизительный материал, чем никакого вовсе.
    if not card.material:
        card.material = (
            material_primary_value
            or material_value
            or material_excluded_value
        )

    # ------------------------------------------------------------
    # FALLBACK: если ни один спек не дал количество (его вообще нет
    # как отдельного поля, оно только в заголовке - как "Носки для
    # девочек, 5 пар", или его нет вообще, потому что characteristics
    # у товара пустые).
    # ------------------------------------------------------------
    if not card.quantity:

        fallback_text = strip_heterogeneous_kit_segments(
            " ".join(filter(None, [card.title, card.description]))
        )
        quantity = extract_quantity(fallback_text)

        if quantity:
            card.quantity = quantity

    # ------------------------------------------------------------
    # МАТЕРИАЛ FALLBACK
    #
    # Если ни один spec-ключ не содержал "материал"/"состав" (Ozon
    # иногда отдаёт материал только текстом внутри описания или ДАЖЕ
    # ТОЛЬКО в заголовке, пробуем вытащить его оттуда же, где это уже
    # делает parser/ozon_parser.py - тем же общим extract_material(),
    # чтобы не поддерживать вторую копию regex.
    # ------------------------------------------------------------
    if not card.material:

        material = extract_material(
            " ".join(filter(None, [card.title, card.description, card.raw_text]))
        )

        if material:
            card.material = material

    card.sections = parsed.get("sections", {})
    card.parser_log = parsed.get("parser_log", [])

    return card

def _extract_volume(value):

    value = str(value or "").strip().lower()

    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)

    match = re.fullmatch(
        r"(\d+(?:[.,]\d+)?)\s*(мл)",
        value,
    )
    if match:
        return f"{match.group(1)} {match.group(2)}"

    return ""
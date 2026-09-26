from resolver.dropdown_axis_resolver import AXIS_RESOLVERS, get_axis_resolver
from utils.dropdown_helpers import variant_display_name
from utils.material_extractor import MATERIAL_GROUP_EN

# Английские канонические токены материала (см. MATERIAL_GROUP_EN) -
# ими по конвенции (обновления (2)/(17) products-dict-gradation-audit.md)
# записывается group материальных dropdown-вариантов. Нужны отдельным
# множеством ниже - см. комментарий у шага 2 в resolve_code().
_ENGLISH_MATERIAL_GROUPS = frozenset(MATERIAL_GROUP_EN.values())

class DropdownResolver:

    DEFAULT_AXES = (
        "material_volume",
        "material_characteristic",
        "material",
        "gender",
        "purpose_category",
        "purpose",
        "mechanism",
    )

    def __init__(self, repository=None):
        self.repository = repository


    def resolve(self, product):

        if not product:
            return ""
        if self.repository is None:
            return ""

        info = self.repository.get(product)

        if not info:
            return ""

        dropdown = info.get("dropdown") or {}
        variants = dropdown.get("variants", [])

        if not variants:
            return ""
        # --------------------------------------------------
        # ДОБАВЛЕНО (жалоба Яна "кабель": наименование определено, но
        # код не проставлен - "там даже выбора нет!", products-dict-
        # gradation-audit.md, обновление 2026-09-25). "Декоративный"
        # dropdown (термин из исходного аудита в начале документа) -
        # когда ВСЕ варианты дают тот же код, что и плоский `code`
        # товара - реальной градации нет вообще, resolve_code() нечего
        # выбирать. Раньше это считалось безопасным ТОЛЬКО потому, что
        # для таких товаров обычно срабатывал общий словарь материалов
        # (result.material) и шаг 3 в decision_engine.py целиком
        # пропускался через material_already_resolved - но это чистое
        # везение: для карточки без единого слова из словаря
        # материалов (частый случай, напр. "USB кабель Type-C") этот
        # гейт не срабатывает, resolve_code() всё равно вызывается, ни
        # одна ось не матчится (group часто чисто описательный, никак
        # не проверяется явно - напр. group='медь' у кабеля), и шаг 4
        # МОЛЧА ЗАТИРАЕТ уже верный плоский код на пустой, хотя
        # выбирать было реально не из чего. Возвращаем "" (как для
        # товара без dropdown вообще) - decision_engine.py тогда
        # просто не трогает уже присвоенный на шаге 2 классификации
        # плоский код.
        # --------------------------------------------------
        flat_code = str(info.get("code", "")).strip()

        if flat_code:

            variant_codes = {
                str(variant.get("code", "")).strip()
                for variant in variants
                if str(variant.get("code", "")).strip()
            }

            if variant_codes and variant_codes == {flat_code}:
                return ""

        return product


    def resolve_code(self, result, card):

        if self.repository is None:
            return

        info = self.repository.get(result.product)

        if not info:
            return

        dropdown = info.get("dropdown") or {}
        variants = dropdown.get("variants", [])

        if not variants:
            return
        # --------------------------------------------------
        # 1. Оси (material / gender / purpose / mechanism / material_volume)
        # --------------------------------------------------
        variant = self._resolve_by_axis(dropdown, variants, card, result)

        if variant:
            self._apply_variant(
                result,
                variant,
                source="DROPDOWN",
                confidence=90,
                review=False,
            )
            return
        # --------------------------------------------------
        # 2. Fallback: ищем group прямо в тексте карточки
        #
        # НАЙДЕНО при разборе жалобы Яна "снова куча ошибок в ручном
        # режиме, легкие позиции убивает неправильный код" (реальные
        # кейсы "точилка"/"браслет" - см. products-dict-gradation-
        # audit.md) - эта проверка исторически рассчитана на group,
        # записанный ПО-РУССКИ (например "ткань"/"фланель" у халата,
        # "автомобиль"/"мебель" у колёс) - там буквальное вхождение
        # осмысленного русского слова в текст карточки действительно
        # неплохой сигнал. Но материальные group по конвенции (см.
        # обновления (2)/(17)) записываются АНГЛИЙСКИМИ токенами
        # (plastic/metal/wood/...) специально для MaterialAxisResolver
        # (шаг 1) и материального фоллбека ниже (шаг 3) - оба сравнивают
        # с ПРАВИЛЬНО извлечённым фактом материала (result.material),
        # а не ищут слово вслепую. Эта же проверка (шаг 2), попадая на
        # такой английский токен, ищет буквальную строку "plastic" ГДЕ
        # УГОДНО в тексте карточки - а такое короткое английское слово
        # нередко залетает случайно (англоязычные спецификации у
        # импортных/דропшип-товаров, "Material: Plastic" на упаковке,
        # артикулы) и не имеет отношения к тому, что реально отличает
        # варианты ЭТОГО товара. Подтверждено синтетически: точилка/
        # браслет с любым случайным "Plastic"/"PLASTIC" в тексте
        # уводились на неверный вариант, хотя ось для них - вовсе не
        # материал. Поэтому для group, совпадающего с одним из
        # английских материальных токенов, эта буквальная проверка
        # пропускается - у материала уже есть свой, куда более
        # аккуратный путь (шаги 1 и 3).
        # --------------------------------------------------
        text = self._build_text(result, card)

        for variant in variants:

            group = str(variant.get("group", "")).strip().lower()

            if not group:
                continue

            if group in _ENGLISH_MATERIAL_GROUPS:
                continue

            if self._contains(text, group):
                self._apply_variant(
                    result,
                    variant,
                    source="DROPDOWN",
                    confidence=90,
                    review=False,
                )
                return
        # --------------------------------------------------
        # 3. Fallback: материал совпадает с name/group варианта
        # --------------------------------------------------
        material = str(result.material or "").strip().lower()

        if material:

            material_candidates = {material}
            english = MATERIAL_GROUP_EN.get(material)
            if english:
                material_candidates.add(english)

            for variant in variants:

                name = str(variant.get("name", "")).strip().lower()
                group = str(variant.get("group", "")).strip().lower()

                if (material_candidates & {name, group}) - {""}:

                    self._apply_variant(
                        result,
                        variant,
                        source="DROPDOWN_MATERIAL",
                        confidence=95,
                        review=False,
                    )
                    return
        # --------------------------------------------------
        # 4. Ничего не определили однозначно.
        #
        # Раньше здесь молча брался ПЕРВЫЙ вариант из списка
        # (result.code = variants[0]["code"]), ставился
        # source="DROPDOWN_FIRST", confidence=60 — и результат
        # выглядел как обычное, пусть не самое уверенное, решение.
        #
        # Диагностика на реальной выборке (100 карточек, см.
        # products-dict-gradation-audit.md, обновление (7)) показала:
        # эта ветка даёт правильный код только в ~22% случаев — хуже,
        # чем случайное угадывание среди вариантов — и при этом
        # confidence/review НИКУДА не попадали в сам Excel (только в
        # консольный лог, который куратор не читает построчно), то
        # есть куратор физически не мог отличить этот угаданный код
        # от настоящего решения. По решению Яна тогда — код НЕ
        # угадывать, оставлять пустым, source="DROPDOWN_UNRESOLVED".
        #
        # ОБНОВЛЕНО (2026-09-25, products-dict-gradation-audit.md,
        # обновление 11) — Ян сначала попросил развернуть это РОВНО
        # для одежды/обуви/головных уборов (ТН ВЭД главы 61/62/64/65):
        # "тут одежда, ставить её надо, но с пометкой проверки, так я
        # буду понимать, что нужно править". Расклад теперь другой,
        # чем в обновлении (7): confidence/review ТЕПЕРЬ доходят до
        # Excel (ozon_auto_processor.apply_result() их показывает), то
        # есть угаданный-но-помеченный код куратор реально отличит от
        # уверенного решения — раньше это было физически невозможно, и
        # именно поэтому в (7) решили не угадывать вовсе.
        #
        # ОБНОВЛЕНО ЕЩЁ РАЗ (2026-09-25, обновление 14) — Ян явно
        # попросил распространить это на ВСЕ товары, не только на
        # одежду: "если мы определили наименование, но не можем
        # выбрать код, то везде ставим 1й код, с пометкой к проверке".
        # is_apparel_footwear_or_headwear()/ограничение по главам
        # 61/62/64/65 больше не проверяется здесь — тот же приём
        # (первый вариант + review=True) применяется к любому товару с
        # неопределившимся dropdown. Импорт is_apparel_footwear_or_
        # headwear оставлен только там, где он ещё реально нужен
        # (engines/decision_engine.py, режим FORCE_AI_NONCLOTHING).
        #
        # alternatives по-прежнему собираем всегда — список кодов, из
        # которых можно выбрать вручную (используется
        # ozon_auto_processor.apply_result(), показывает куратору
        # варианты прямо в Excel).
        # --------------------------------------------------
        result.alternatives = {
            item.get("code", ""): variant_display_name(item)
            for item in variants
            if item.get("code")
        }

        first_with_code = next(
            (v for v in variants if str(v.get("code", "")).strip()),
            None,
        )

        if first_with_code:
            self._apply_variant(
                result,
                first_with_code,
                source="DROPDOWN_FIRST",
                confidence=30,
                review=True,
            )
            return

        result.code = ""
        result.dropdown_group = ""
        result.dropdown = ""
        result.review = True
        result.source = "DROPDOWN_UNRESOLVED"
        result.confidence = 0
    # ==========================================================
    # AXIS DISPATCH
    # ==========================================================
    def _resolve_by_axis(self, dropdown, variants, card, result):
        """
        Если у dropdown указана конкретная "axis" - используем
        только её. Иначе пробуем оси по умолчанию по очереди,
        пока какая-то не вернёт вариант.
        """

        explicit_axis = dropdown.get("axis")

        if explicit_axis:

            resolver = get_axis_resolver(explicit_axis)

            return resolver.find(variants, card, result)

        for axis in self.DEFAULT_AXES:

            resolver = AXIS_RESOLVERS.get(axis)

            if not resolver:
                continue

            variant = resolver.find(variants, card, result)

            if variant:
                return variant

        return None
    # ==========================================================
    # APPLY VARIANT
    # ==========================================================
    def _apply_variant(self, result, variant, source, confidence, review):
        code = str(variant.get("code", "")).strip()

        if not code:
            return

        result.code = code
        result.dropdown_group = str(variant.get("group", "")).strip()
        result.dropdown = variant_display_name(variant)
        result.source = source
        result.confidence = confidence
        result.review = review
    # ==========================================================
    # TEXT
    # ==========================================================
    def _build_text(self, result, card):

        parts = [
            getattr(card, "title", ""),
            getattr(card, "description", ""),
            getattr(card, "cleaned_text", ""),
            getattr(card, "slug", ""),
            getattr(card, "material", ""),
            getattr(result, "material", ""),
        ]
        specs = getattr(card, "specs", {}) or {}

        for key, value in specs.items():

            parts.append(str(key))
            parts.append(str(value))

        return " ".join(
            str(value)
            for value in parts
            if value
        ).lower()
    # ==========================================================
    # MATCH
    # ==========================================================
    def _contains(self, text, value):

        if not text or not value:
            return False

        value = value.lower().strip()

        if not value:
            return False
        return value in text
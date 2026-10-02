from resolver.dropdown_axis_resolver import AXIS_RESOLVERS, get_axis_resolver, prefer_by_words
from utils.dropdown_helpers import variant_display_name
from utils.groups import canon, is_standard

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
            self._flag_shared_group(result, variant, variants)
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

            group = canon(variant.get("group", ""))

            if not group:
                continue

            # Стандартные группы (материал / пол / характеристика /
            # назначение - utils/groups.py) уже проверены осями выше по
            # своим словарям; буквальный поиск названия группы в тексте -
            # только для своих групп товара ("кнопочный", "крестообразный").
            # Раньше так пропускались английские материалы, а остальные
            # английские группы в русском тексте просто не находились.
            if is_standard(group):
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

        # Если у товара явно задан список осей и материала в нём нет
        # (вариант выбирается по слову - 2026-10-01, слияние групп),
        # материал не должен выбирать вариант и здесь.
        explicit_axis = dropdown.get("axis")

        if explicit_axis:
            axes = explicit_axis if isinstance(explicit_axis, (list, tuple)) else [explicit_axis]
            if not any(a in ("material", "material_volume", "material_characteristic") for a in axes):
                material = ""

        if material:

            material_candidates = {canon(material)}

            matched = [
                v for v in variants
                if (material_candidates & {canon(v.get("name", "")), canon(v.get("group", ""))}) - {""}
            ]
            chosen = prefer_by_words(matched, card) if matched else None

            if chosen:
                self._apply_variant(
                    result,
                    chosen,
                    source="DROPDOWN_MATERIAL",
                    confidence=95,
                    review=False,
                )
                self._flag_shared_group(result, chosen, variants)
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

        # Товар-категория (2026-10-01): у каждого влитого товара свой
        # код по умолчанию - "миска" металл, "кружка" керамика. Если
        # материал не определился, берём код того товара, чьё слово
        # стоит в наименовании карточки.
        # материал словом в заголовке в другой форме ("пластиковые
        # миски", "из стекла") - общий словарь его не поймал
        if dropdown.get("defaults") and not result.material:
            variant = self._title_material_variant(variants, card)
            if variant:
                self._apply_variant(
                    result, variant, source="DROPDOWN_MATERIAL", confidence=80, review=False,
                )
                return

        default = self._synonym_default(dropdown, card)

        if default:
            code, review = default
            variant = next(
                (v for v in variants if str(v.get("code", "")).strip() == code),
                {"code": code, "group": ""},
            )
            variant = self._fit_volume(variant, variants, card)
            self._apply_variant(
                result,
                variant,
                source="DROPDOWN_DEFAULT",
                confidence=50 if review else 80,
                review=review,
            )
            return

        # У товара есть свой плоский код ("чехол": 4202199000 + один
        # вариант 6306120000 "оксфорд") - он и есть код по умолчанию.
        # Раньше при несработавших осях его затирал первый вариант, и
        # силиконовый чехол получал код брезента (2026-09-29).
        flat_code = str(info.get("code", "")).strip()

        if flat_code:
            result.alternatives = {
                flat_code: result.product,
                **result.alternatives,
            }
            result.code = flat_code
            return

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
            # ИСПРАВЛЕНО (2026-09-26, products-dict-gradation-audit.md,
            # обновление 16) - раньше "axis" мог быть только ОДНОЙ
            # строкой (одна ось, и ничего больше). Разбор жалобы Яна
            # на "держатель": карточка магнитного держателя для
            # телефона ("Магнитное крепление...", в описании явно
            # "Материал: алюминиевый сплав") получала металлический
            # вариант, хотя в dropdown у "держатель" ЕСТЬ отдельный
            # магнитный вариант (group='magnet', match=['магнитный',
            # 'иголок']) - именно то, что просил Ян. Причина - порядок
            # DEFAULT_AXES ниже: "material_characteristic" проверяется
            # РАНЬШЕ "purpose" - материал "металл" (честно определённый
            # по тексту, алюминиевый сплав - это металл) находит среди
            # металлических вариантов держателя ОБА (обычный и
            # "бытовой"/органайзер), не находит явную характеристику в
            # тексте - и молча берёт "дефолтный" металлический вариант
            # как есть, даже не пытаясь проверить более специфичный,
            # явно curated список match-слов у магнитного варианта.
            # Собственный match-список товара ("магнитный"/"иголок",
            # "защелки"/"удлинители"/"автомобильные" и т.п.) - более
            # точный, целенаправленно подобранный сигнал именно для
            # ЭТОГО товара, чем общий факт материала, и должен
            # проверяться раньше. Глобально менять порядок
            # DEFAULT_AXES для ВСЕХ товаров с dropdown нельзя - это
            # ломает другие товары с похожей структурой (например
            # "поилка": слово "вода" почти гарантированно есть в
            # ЛЮБОЙ карточке автопоилки, и если проверять
            # purpose_category раньше материала, обычная пластиковая
            # поилка без автоматического фонтана стала бы всегда
            # получать код автоматической поилки-фонтана только за
            # упоминание слова "вода") - поэтому вместо глобальной
            # правки "axis" теперь можно быть СПИСКОМ осей,
            # проверяемых по порядку ТОЛЬКО для конкретного товара,
            # у которого это явно указано в словаре (см. 'держатель'
            # в products.py - axis=['purpose', 'material_characteristic',
            # 'material']) - остальные товары (одна строка axis или
            # её отсутствие вовсе) ведут себя ТОЧНО как раньше.
            axis_names = (
                explicit_axis
                if isinstance(explicit_axis, (list, tuple))
                else [explicit_axis]
            )

            for axis_name in axis_names:

                resolver = get_axis_resolver(axis_name)
                variant = resolver.find(variants, card, result)

                if variant:
                    return variant

            return None

        for axis in self.DEFAULT_AXES:

            resolver = AXIS_RESOLVERS.get(axis)

            if not resolver:
                continue

            # у товара-категории при неизвестном материале объём не
            # выбирает вариант вслепую - сработает код по слову товара
            if axis == "material_volume" and dropdown.get("defaults") and not result.material:
                continue

            variant = resolver.find(variants, card, result)

            if variant:
                return variant

        return None
    # ==========================================================
    # APPLY VARIANT
    # ==========================================================
    # ==========================================================
    # ОДНА ГРУППА - НЕСКОЛЬКО КОДОВ (2026-09-29)
    #
    # После замены заглушки group="other" на группы по коду ТН ВЭД
    # (utils/code_groups.py) у части товаров два варианта с разными
    # кодами оказались в одной группе, и куратор ставил оба почти
    # одинаково часто (например "игрушечная машинка": 9503009909 и
    # 9503008500 - обе toys). Ось по тексту их не различит - выбирается
    # первый, более частый. Уверенным такой выбор считать нельзя:
    # ставим пометку на проверку и отдаём альтернативы в Excel.
    # Вариант со своими match-словами выбран по ним - это не догадка.
    # ==========================================================
    def _flag_shared_group(self, result, variant, variants):

        if variant.get("match"):
            return

        group = canon(variant.get("group", ""))
        code = str(variant.get("code", "")).strip()

        if not group:
            return

        # Сосед со своими словами (match) - частный случай, которого в
        # карточке нет (иначе выбрали бы его); общий вариант тогда не
        # спорный. Спорны соседи без слов и соседи с порогом объёма.
        siblings = [
            item for item in variants
            if canon(item.get("group", "")) == group
            and (
                not item.get("match")
                or item.get("min_volume_l") is not None
                or item.get("max_volume_l") is not None
            )
            and str(item.get("code", "")).strip() not in ("", code)
        ]

        if not siblings:
            return

        result.review = True
        result.confidence = min(result.confidence or 60, 60)
        result.source = f"{result.source}_AMBIGUOUS"
        result.alternatives = {
            item.get("code", ""): variant_display_name(item)
            for item in [variant] + [v for v in variants if v is not variant]
            if item.get("code")
        }

    @staticmethod
    def _fit_volume(variant, variants, card):
        """Код по умолчанию с порогом объёма ("канистра" -> до 2 л), а в
        карточке 20 л - берём вариант того же материала с подходящим
        порогом."""

        bounded = lambda v: v.get("min_volume_l") is not None or v.get("max_volume_l") is not None

        if not bounded(variant):
            return variant

        from resolver.dropdown_axis_resolver import MaterialVolumeAxisResolver

        volume = MaterialVolumeAxisResolver()._extract_volume_liters(card)

        if volume is None:
            return variant

        group = canon(variant.get("group", ""))

        for other in variants:
            if canon(other.get("group", "")) != group or not bounded(other):
                continue
            min_v, max_v = other.get("min_volume_l"), other.get("max_volume_l")
            if max_v is not None and volume > float(max_v):
                continue
            if min_v is not None and volume <= float(min_v):
                continue
            return other

        return variant

    _TITLE_MATERIAL_STEMS = (
        ("пластик", "пластик"), ("силикон", "пластик"), ("акрил", "пластик"),
        ("металл", "металл"), ("нержав", "металл"), ("стал", "металл"), ("алюмин", "металл"),
        ("чугун", "металл"), ("медн", "металл"), ("латун", "металл"),
        ("стекл", "стекло"), ("стеклян", "стекло"),
        ("керами", "керамика"), ("фарфор", "керамика"), ("фаянс", "керамика"),
        ("дерев", "дерево"), ("бамбук", "дерево"),
        ("бумаж", "бумага"), ("картон", "бумага"),
    )

    def _title_material_variant(self, variants, card):

        import re

        title = str(getattr(card, "title", "") or "").lower()

        found = []

        for stem, group in self._TITLE_MATERIAL_STEMS:
            match = re.search(r"(?<!\w)" + stem + r"\w*", title)
            if match:
                found.append((match.start(), group))

        for _pos, group in sorted(found):
            for variant in variants:
                if canon(variant.get("group", "")) == group and not variant.get("require_words"):
                    return variant

        return None

    @staticmethod
    def _synonym_default(dropdown, card):
        """(код, нужна ли проверка) по dropdown["defaults"] - {слово:
        {"code", "review"}} - для слова, которое раньше всех стоит в
        заголовке (потом в описании)."""

        import re

        defaults = dropdown.get("defaults") or {}

        if not defaults:
            return None

        for field in ("title", "description"):

            text = str(getattr(card, field, "") or "").lower()

            if not text:
                continue

            best = None

            for word, rule in defaults.items():
                match = re.search(r"(?<!\w)" + re.escape(str(word).lower()) + r"\w*", text)
                if match and (best is None or match.start() < best[0]):
                    rule = rule if isinstance(rule, dict) else {"code": rule, "review": True}
                    best = (match.start(), str(rule.get("code", "")).strip(), bool(rule.get("review", True)))

            if best and best[1]:
                return best[1], best[2]

        return None

    def _apply_variant(self, result, variant, source, confidence, review):
        code = str(variant.get("code", "")).strip()

        if not code:
            return

        result.code = code
        result.dropdown_group = canon(variant.get("group", ""))
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
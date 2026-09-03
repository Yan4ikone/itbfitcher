import re
from collections import Counter

from cleaner.alias_builder import AliasBuilder
from learning.learning_filters import (
    extract_dropdown_keywords,
    is_valid_alias,
    normalize_material,
)
from learning.name_normalizer import normalize_dictionary_name
from learning.product_matcher import ProductMatcher
from utils.material_extractor import is_excluded_material_key, MATERIAL_GROUP_EN
from utils.gender_extractor import find_known_gender

from learning.review_models import (
    LearningReport,
    NewProduct,
    NewAlias,
    NewDropdownVariant,
    NewDropdownMatchWords,
    NewDropdownCandidate,
    NewPattern,
    NewDictionaryWord,
)


class LearningAnalyzer:

    # Сколько РАЗНЫХ кодов должно накопиться у товара без dropdown,
    # чтобы предложить завести для него dropdown. Именно РАЗНЫХ - а
    # не суммарных наблюдений: "держатель из металла" в одном файле
    # и "держатель из пластика" в другом файле - каждый код при этом
    # встретится ровно один раз, но для одного и того же наименования
    # код УЖЕ разошёлся - этого достаточно как сигнала.
    MIN_DROPDOWN_DISTINCT_CODES = 2

    # Сколько раз минимум должен встретиться КАЖДЫЙ ИЗ ЭТИХ кодов.
    # Раньше стояло 2 - из-за этого сценарий выше никогда не долавливал
    # порог (каждый код видели по одному разу за сеанс обучения).
    # Единичного наблюдения достаточно: сам факт "то же наименование,
    # другой код" уже показывает куратор своей ручной правкой -
    # опечатка исключена, потому что код подтверждён человеком, а не
    # угадан автоматически.
    MIN_DROPDOWN_CODE_OCCURRENCES = 1

    def __init__(self, runtime):

        self.runtime = runtime
        self.matcher = ProductMatcher(runtime.product_repository)
        self.alias_builder = AliasBuilder()
        # product_name -> Counter(code -> сколько раз встретился)
        # Накапливается по ходу analyze(), используется в конце для
        # _analyze_dropdown_candidates(). Не хранит "0"/пустые коды
        # и коды, уже объяснённые material_codes товара.
        self._code_observations = {}
    # ==========================================================
    # PUBLIC
    # ==========================================================
    def analyze(self):

        print("ANALYZER START")
        report = LearningReport()
        self._code_observations = {}
        self._code_keywords = {}
        self._unknown_word_index = {}   # (dictionary, word) -> NewDictionaryWord

        for card in self.runtime.all_cards():

            url = card.get("url")

            if self.runtime.is_learning_processed(url):
                continue

            print("\n" + "=" * 70)
            print("CARD:", url)
            manual = self.runtime.manual.get(
                card.get("normalized_url", url))

            if not manual:
                continue
            if url:
                report.processed_cards.append(url)

            print("NORMALIZED:", card.get("normalized_url"))
            print("MANUAL:", manual)
            description = self._get_description(manual)

            if not description:
                continue

            code = self._get_code(manual)

            if not code:
                continue

            material, raw_material = self._get_material(card)
            print("DESCRIPTION:", description)
            print("CODE:", code)
            print("MATERIAL:", material)
            product_name, product_info = (self._resolve_product(
                    report,
                    card,
                    description,
                    code,
                    material
                )
            )
            if not product_name:
                continue

            print("PRODUCT NAME:", product_name)
            # --------------------------------------------------
            # НЕИЗВЕСТНОЕ СЛОВО СЛОВАРЯ
            #
            # raw_material непустой, но normalize_material() (внутри
            # _get_material) не смог сопоставить его ни с одним
            # известным материалом - значит это, возможно, ПОДЛИННО
            # новое слово (напр. "неопрен"), а не просто "материал
            # известен, но для этого товара ещё нет кода" (это ниже,
            # в _analyze_material).
            # --------------------------------------------------
            if raw_material and not material:
                self._analyze_unknown_word(
                    report,
                    dictionary="material",
                    word=raw_material,
                    product_name=product_name,
                )

            raw_gender = self._find_spec_gender(card.get("specs", {}) or {})

            if raw_gender and not find_known_gender(raw_gender):
                self._analyze_unknown_word(
                    report,
                    dictionary="gender",
                    word=raw_gender,
                    product_name=product_name,
                )
            # --------------------------------------------------
            # DROPDOWN CANDIDATE OBSERVATION
            #
            # Копим статистику ДО остальных шагов, чтобы учесть
            # даже те карточки, для которых material/alias/pattern
            # анализ ничего нового не даст.
            # --------------------------------------------------
            self._observe_code(product_name, product_info, code, card, description)
            # --------------------------------------------------
            # MATERIAL
            # --------------------------------------------------
            self._analyze_material(
                report,
                product_name,
                product_info,
                material,
                code
            )
            # --------------------------------------------------
            # ALIASES
            # --------------------------------------------------
            self._analyze_aliases(
                report,
                card,
                product_name,
                product_info,
                description
            )
            # --------------------------------------------------
            # DROPDOWN
            # --------------------------------------------------
            self._analyze_dropdown(
                report,
                card,
                description,
                product_name,
                code
            )
            # --------------------------------------------------
            # PATTERNS
            # --------------------------------------------------
            self._analyze_patterns(
                report,
                card,
                product_name,
                product_info
            )
        # --------------------------------------------------
        # DROPDOWN CANDIDATES (по накопленной статистике)
        # --------------------------------------------------
        self._analyze_dropdown_candidates(report)
        self._print_report(report)

        return report
    # ==========================================================
    # DESCRIPTION
    # ==========================================================
    def _get_description(self, manual):

        raw_description = str(manual.get("description", "")).strip()

        if not raw_description:
            return ""

        return (
            normalize_dictionary_name(raw_description)
            .lower()
            .strip()
        )
    # ==========================================================
    # CODE
    # ==========================================================
    def _get_code(self, manual):

        code = str(manual.get("code", "")).strip()

        if not code:
            return ""
        if code in ("0", "nan", "none"):
            return ""
        return code
    # ==========================================================
    # PRODUCT
    # ==========================================================
    def _resolve_product(
            self,
            report,
            card,
            description,
            code,
            material
    ):
        runtime_product = (self.runtime.get_product(description))
        print("PRODUCT EXISTS:", runtime_product)
        # --------------------------------------------------
        # PRODUCT ALREADY EXISTS
        # --------------------------------------------------
        if runtime_product:
            product_name = (self._resolve_product_name(description, runtime_product))
            product_info = (self.runtime.get_product(product_name) or {})

            return (product_name, product_info)
        # --------------------------------------------------
        # TRY MATCHING
        # --------------------------------------------------
        matched = self.matcher.match(description, code)
        print("MATCH:", matched)

        if matched:
            product_name = matched["product"]
            product_info = (self.runtime.get_product(product_name) or {})
            self._add_alias(report, product_name, product_info, description)

            return (product_name, product_info)


        dropdown_product = self._find_product_by_dropdown_code(code)
        print("DROPDOWN MATCH:", dropdown_product)

        if dropdown_product:
            product_info = (self.runtime.get_product(dropdown_product) or {})
            self._add_alias(report, dropdown_product, product_info, description)

            return (dropdown_product, product_info)

        report.new_products.append(
            NewProduct(
                description=description,
                code=code,
                title=str(card.get("title", "")),
                url=str(card.get("url", "")),
                material=material))
        print("NEW PRODUCT:", description, code)

        return None, {}

    # ==========================================================
    # DROPDOWN CODE REVERSE LOOKUP
    # ==========================================================
    def _find_product_by_dropdown_code(self, code):

        code = str(code).strip()

        if not code:
            return None

        for product_name, info in self.runtime.all_products():

            dropdown = info.get("dropdown") or {}
            variants = dropdown.get("variants", []) or []

            for variant in variants:

                if str(variant.get("code", "")).strip() == code:
                    return product_name

        return None
    # ==========================================================
    # PRODUCT NAME
    # ==========================================================
    def _resolve_product_name(self, description, runtime_product):

        if (isinstance(runtime_product, dict)
                and "product" in runtime_product):
            return runtime_product["product"]
        return description
    # ==========================================================
    # MATERIAL
    # ==========================================================
    # ==========================================================
    # MATERIAL
    # ==========================================================
    def _find_spec_material(self, specs, prefer_upper):
        """Ищет материал среди характеристик, сознательно игнорируя
        стельку/подкладку/подошву (см. utils.material_extractor).

        prefer_upper=True - ищем только явные ключи материала ОСНОВНОЙ
        части товара ("материал верха" и т.п.).
        prefer_upper=False - ищем любой ключ "материал"/"состав",
        кроме относящихся к вспомогательным частям.
        """

        if not isinstance(specs, dict):
            return ""

        for key, value in specs.items():

            if not value:
                continue

            key_l = str(key).strip().lower()

            if is_excluded_material_key(key_l):
                continue

            if prefer_upper:
                if "верх" not in key_l:
                    continue
            else:
                if not ("материал" in key_l or "состав" in key_l):
                    continue

            return str(value).strip().lower()

        return ""

    def _find_spec_gender(self, specs):
        """Ищет пол/возрастную группу среди характеристик по явному
        ключу ("Пол", "Пол товара") - по тому же принципу, что
        _find_spec_material ищет материал. Не путать со свободным
        текстом заголовка/описания - там пол ищет GenderAxisResolver
        (resolver/dropdown_axis_resolver.py) напрямую через
        find_known_gender, без явного ключа."""

        if not isinstance(specs, dict):
            return ""

        for key, value in specs.items():

            if not value:
                continue

            key_l = str(key).strip().lower()

            if key_l not in ("пол", "пол товара"):
                continue

            return str(value).strip().lower()

        return ""

    def _get_material(self, card):

        raw_material = str(
            card.get(
                "material",
                ""
            )
            or ""
        ).strip().lower()

        if not raw_material:

            specs = (
                    card.get(
                        "specs",
                        {}
                    )
                    or {}
            )

            # Приоритет: "Материал верха" (или похожие ключи основной
            # части товара) - раньше искали только точное "Материал"/
            # "материал", и если у WB характеристика называлась
            # "Материал верха" (частый случай для обуви/сумок), она
            # вообще не находилась, хотя это и есть основной материал.
            raw_material = self._find_spec_material(
                specs,
                prefer_upper=True,
            )

        if not raw_material:

            specs = (
                    card.get(
                        "specs",
                        {}
                    )
                    or {}
            )

            raw_material = self._find_spec_material(
                specs,
                prefer_upper=False,
            )

        if not raw_material:
            return "", ""

        material = normalize_material(
            raw_material
        )
        print(
            "MATERIAL:",
            repr(raw_material),
            "->",
            repr(material)
        )
        return material, raw_material
    # ==========================================================
    # НЕИЗВЕСТНОЕ СЛОВО СЛОВАРЯ
    # ==========================================================
    def _analyze_unknown_word(self, report, dictionary, word, product_name):
        """
        word - сырое значение, которое не подтвердилось НИ ОДНИМ
        известным словом из соответствующего словаря (см. вызов в
        analyze()). Дедуплицируем по (dictionary, word) - одно и то
        же неизвестное слово может встретиться в десятках карточек
        за один прогон, куратору нужно увидеть его ОДИН раз со
        счётчиком, а не сотню одинаковых строк.
        """

        word = str(word).strip().lower()

        if not word:
            return

        # Полностью числовые/технические значения ("0x17.0x24",
        # артикулы) - не показываем как кандидата в словарь, это
        # мусор, а не слово.
        if not re.search(r"[a-zа-я]", word):
            return

        key = (dictionary, word)

        existing = self._unknown_word_index.get(key)

        if existing:
            existing.count += 1
            return

        item = NewDictionaryWord(
            dictionary=dictionary,
            word=word,
            product=product_name,
            count=1,
        )

        self._unknown_word_index[key] = item
        report.new_dictionary_words.append(item)
    # ==========================================================
    # MATERIAL ANALYSIS
    # ==========================================================
    def _analyze_material(
            self,
            report,
            product_name,
            product_info,
            material,
            code
    ):
        """
        material - уже провалидированный факт (найден в MATERIAL_ALIASES,
        см. _get_material/normalize_material). Раньше здесь предлагалось
        отдельное "material -> код" в material_codes (NewMaterialCode).
        Теперь material_codes новыми записями не пополняется - вместо
        этого предлагаем dropdown-вариант с group=material: тот же
        механизм "факт -> код для товара", что и для любого другого
        dropdown-варианта (см. NewDropdownVariant.group), только
        источник факта - общий словарь материалов, а не product-
        специфичный список.
        """

        if not material or not code:
            return

        # 1. Уже покрыто ЛЕГАСИ-путём (material_codes у товара) -
        # ничего предлагать не нужно, этот путь по-прежнему читается
        # резолвером как есть (см. resolver/material_resolver.py).
        known_materials = {
            str(key).strip().lower()
            for key in (product_info.get("material_codes", {}) or {})
        }

        if material in known_materials:
            return

        # 2. Уже покрыто СУЩЕСТВУЮЩИМ dropdown-вариантом - сравниваем
        # и русское каноническое имя, и его английский эквивалент,
        # т.к. group у разных товаров исторически записан в разных
        # конвенциях (см. utils.material_extractor.MATERIAL_GROUP_EN).
        group_candidates = {material}
        english = MATERIAL_GROUP_EN.get(material)
        if english:
            group_candidates.add(english)

        existing_variants = (
            (product_info.get("dropdown") or {}).get("variants", [])
            or []
        )
        existing_groups = {
            str(v.get("group", "")).strip().lower()
            for v in existing_variants
        }

        if group_candidates & existing_groups:
            return

        # 3. Уже предложено в ЭТОМ ЖЕ прогоне (в т.ч. другой карточкой
        # с тем же product+code, или отдельно _analyze_dropdown -
        # общий dedup по report.new_dropdown_variants).
        for item in report.new_dropdown_variants:
            if item.product == product_name and str(item.code).strip() == str(code).strip():
                return

        group = english or material

        report.new_dropdown_variants.append(
            NewDropdownVariant(
                product=product_name,
                code=code,
                name=material.capitalize(),
                group=group,
                match=(),
            )
        )

        print(
            "NEW MATERIAL DROPDOWN VARIANT:",
            product_name,
            material,
            "->",
            group,
            code
        )
    # ==========================================================
    # ALIAS
    # ==========================================================
    def _add_alias(
            self,
            report,
            product,
            product_info,
            alias
    ):

        alias = (
            normalize_dictionary_name(
                alias
            )
            .lower()
            .strip()
        )

        if not alias:
            return

        if not is_valid_alias(alias, product):
            print(
                "ALIAS FILTER:",
                repr(alias)
            )
            return

        # --------------------------------------------------
        # ДЕДУП
        #
        # Раньше этой проверки не было вообще: если описание одной
        # и той же карточки (или просто похожие описания у разных
        # карточек) матчилось на уже известный товар через
        # ProductMatcher, _add_alias вызывался на КАЖДОЙ такой
        # карточке и без остановки пушил в report.new_aliases
        # одинаковую пару (product, alias) - отсюда буквальные дубли
        # строк в окне обучения.
        # --------------------------------------------------
        known_aliases = {
            normalize_dictionary_name(existing).lower().strip()
            for existing in (product_info.get("aliases", []) or [])
        }

        if alias in known_aliases:
            return

        already_pending = any(
            item.product == product and item.alias == alias
            for item in report.new_aliases
        )

        if already_pending:
            return

        report.new_aliases.append(
            NewAlias(
                product=product,
                alias=alias
            )
        )
    # ==========================================================
    # ALIASES ANALYSIS
    # ==========================================================
    def _analyze_aliases(
            self,
            report,
            card,
            product_name,
            product_info,
            description
    ):
        aliases = {normalize_dictionary_name(alias)
            .lower()
            .strip()

            for alias in (product_info.get("aliases", []) or [])
        }
        aliases.add(normalize_dictionary_name(product_name)
            .lower()
            .strip()
        )
        pending_aliases = {
            (
                item.product,
                normalize_dictionary_name(item.alias).lower().strip()
            )
            for item in report.new_aliases
        }
        candidate_aliases = (
            self.alias_builder.build(card, description))

        for alias in candidate_aliases:

            alias = (normalize_dictionary_name(alias)
                .lower()
                .strip()
            )
            if not alias:
                continue

            if alias in aliases:
                continue

            if not is_valid_alias(alias, product_name):
                print("ALIAS FILTER:", repr(alias))
                continue

            key = (product_name, alias)

            if key in pending_aliases:
                continue

            report.new_aliases.append(
                NewAlias(
                    product=product_name,
                    alias=alias
                )
            )
            pending_aliases.add(key)
            aliases.add(alias)
    # ==========================================================
    # DROPDOWN
    # ==========================================================
    def _analyze_dropdown(self, report, card, description, product_name, code):

        product_info = (
                self.runtime.get_product(product_name)
                or {}
        )

        default_code = str(
            product_info.get("code", "")).strip()

        if not default_code:
            return

        if code == default_code:
            return

        material_codes = {
            str(value).strip()
            for value in (
                    product_info.get(
                        "material_codes",
                        {}
                    )
                    or {}
            ).values()
        }
        if code in material_codes:
            return

        dropdown = product_info.get("dropdown") or {}
        if not dropdown:
            return

        existing_variants = dropdown.get("variants", []) or []

        known_codes = {
            str(item.get("code", "")).strip()
            for item in existing_variants
        }

        keywords = extract_dropdown_keywords(card, description, product_name)

        if code in known_codes:
            # Код уже есть среди вариантов - не дублируем вариант, но
            # если у карточки нашлись НОВЫЕ слова, которых пока нет в
            # match этого варианта - предложим его расширить (см.
            # NewDropdownMatchWords). Это и есть "расширение зонтика"
            # без ручного набора текста куратором.
            if not keywords:
                return

            variant = next(
                (
                    v for v in existing_variants
                    if str(v.get("code", "")).strip() == code
                ),
                None,
            )

            if variant is None:
                return

            known_words = {
                str(w).strip().lower()
                for w in variant.get("match", [])
            }

            new_words = tuple(w for w in keywords if w not in known_words)

            if not new_words:
                return

            for item in report.new_dropdown_match_words:
                if item.product == product_name and item.code == code:
                    return

            report.new_dropdown_match_words.append(
                NewDropdownMatchWords(
                    product=product_name,
                    code=code,
                    words=new_words,
                )
            )
            print("EXTEND DROPDOWN MATCH:", product_name, code, new_words)
            return

        for item in report.new_dropdown_variants:

            if (item.product == product_name and str(item.code).strip() == code):
                return

        name = keywords[0].capitalize() if keywords else ""

        report.new_dropdown_variants.append(
            NewDropdownVariant(
                product=product_name,
                code=code,
                name=name,
                match=keywords,
            )
        )
        print("NEW DROPDOWN:", product_name, code, name, keywords)
    # ==========================================================
    # DROPDOWN CANDIDATE - НАБЛЮДЕНИЕ
    # ==========================================================
    def _observe_code(self, product_name, product_info, code, card, description):
        """
        Копит, какие коды встречались у товара БЕЗ dropdown, чтобы
        в конце analyze() решить, не пора ли завести ему dropdown.

        Намеренно НЕ учитывает:
        - товары, у которых dropdown уже есть (там за новые варианты
          отвечает _analyze_dropdown - по одной строке за раз);
        - коды "0"/пустые;
        - коды, которые уже объясняются известным material_codes
          товара - там расхождение кодов это нормальная работа
          материалов, а не сигнал "нужен dropdown".
        """

        code = str(code).strip()

        if not code or code == "0":
            return

        if product_info.get("dropdown"):
            return

        known_material_codes = {
            str(value).strip()
            for value in (
                product_info.get("material_codes", {}) or {}
            ).values()
            if str(value).strip()
        }

        if code in known_material_codes:
            return

        counter = self._code_observations.setdefault(
            product_name,
            Counter()
        )
        counter[code] += 1

        # Копим слова-кандидаты в match для КАЖДОГО кода отдельно -
        # чтобы при заведении нового dropdown (см.
        # _analyze_dropdown_candidates) варианты сразу получили
        # осмысленное name/match, а не "Авто 1"/"Авто 2".
        keywords = extract_dropdown_keywords(card, description, product_name)

        if keywords:
            self._code_keywords.setdefault(
                product_name, {}
            ).setdefault(code, set()).update(keywords)
    # ==========================================================
    # DROPDOWN CANDIDATE - РЕШЕНИЕ
    # ==========================================================
    def _analyze_dropdown_candidates(self, report):

        for product_name, counter in self._code_observations.items():

            distinct_codes = [
                code
                for code, count in counter.items()
                if count >= self.MIN_DROPDOWN_CODE_OCCURRENCES
            ]

            if len(distinct_codes) < self.MIN_DROPDOWN_DISTINCT_CODES:
                continue

            codes = tuple(
                sorted(
                    counter.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )

            keywords = tuple(
                (code, tuple(self._code_keywords.get(product_name, {}).get(code, ())))
                for code, _count in codes
            )

            report.new_dropdown_candidates.append(
                NewDropdownCandidate(
                    product=product_name,
                    codes=codes,
                    keywords=keywords,
                )
            )

            print(
                "NEW DROPDOWN CANDIDATE:",
                product_name,
                codes
            )
    # ==========================================================
    # PATTERNS
    # ==========================================================
    def _analyze_patterns(
            self,
            report,
            card,
            product_name,
            product_info
    ):
        known_patterns = {
            str(pattern)
            .strip()
            .lower()
            for pattern in (
                    product_info.get(
                        "patterns",
                        []
                    )
                    or []
            )
        }
        description = (
            str(
                card.get(
                    "description",
                    ""
                )
                or ""
            )
            .strip()
            .lower()
        )
        if not description:
            return

        normalized_product = (
            product_name
            .strip()
            .lower()
        )
        if not normalized_product:
            return

        if description == normalized_product:
            return

        product_words = (normalized_product.split())

        if len(product_words) != 1:
            return

        word = product_words[0]

        if len(word) < 9:
            return

        # --------------------------------------------------
        # Ищем основу слова в описании.
        # --------------------------------------------------

        stem_length = max(4, len(word) - 2)
        stem = word[:stem_length]

        if stem not in description:
            return

        pattern = (
            rf"{re.escape(stem)}.*"
        )
        normalized_pattern = (
            pattern
            .strip()
            .lower()
        )
        if normalized_pattern in known_patterns:
            return

        report.new_patterns.append(
            NewPattern(product=product_name, pattern=pattern))
        print("NEW PATTERN:", product_name, pattern)

    # ==========================================================
    # REPORT
    # ==========================================================

    def _print_report(self, report):
        print("\n" + "=" * 70)
        print("ANALYZER FINISH")
        print("NEW PRODUCTS:", len(report.new_products))
        print("NEW ALIASES:", len(report.new_aliases))
        print("NEW DROPDOWNS:", len(report.new_dropdown_variants))
        print("NEW DROPDOWN CANDIDATES:", len(report.new_dropdown_candidates))
        print("NEW PATTERNS:", len(report.new_patterns))
        print("NEW DICTIONARY WORDS:", len(report.new_dictionary_words))
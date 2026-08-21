import re

from cleaner.alias_builder import AliasBuilder
from learning.learning_filters import is_valid_alias
from learning.name_normalizer import normalize_dictionary_name
from learning.product_matcher import ProductMatcher

from learning.review_models import (
    LearningReport,
    NewProduct,
    NewAlias,
    NewMaterialCode,
    NewDropdownVariant,
    NewPattern,
)


class LearningAnalyzer:

    def __init__(self, runtime):

        self.runtime = runtime
        self.matcher = ProductMatcher(runtime.product_repository)
        self.alias_builder = AliasBuilder()
    # ==========================================================
    # PUBLIC
    # ==========================================================
    def analyze(self):

        print("ANALYZER START")
        report = LearningReport()

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

            material = self._get_material(card)
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
            self._add_alias(report, product_name, description)
            product_info = (self.runtime.get_product(product_name) or {})

            return (product_name, product_info)
        # --------------------------------------------------
        # КОД УЖЕ ИЗВЕСТЕН КАК ВАРИАНТ В DROPDOWN_LISTS.PY
        #
        # products.py и dropdown_lists.py - два разных словаря, и
        # раньше сопоставление смотрело только в products.py. Если
        # код уже существует как вариант дропдауна какого-то товара
        # (например "контейнер" -> вариант "Текстиль" с этим кодом),
        # это ЗНАКОМЫЙ код, а не новый товар - нельзя заводить для
        # него отдельную несвязанную запись в products.py.
        # --------------------------------------------------
        dropdown_product = self._find_product_by_dropdown_code(code)
        print("DROPDOWN MATCH:", dropdown_product)

        if dropdown_product:
            self._add_alias(report, dropdown_product, description)
            product_info = (self.runtime.get_product(dropdown_product) or {})

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

        for product_name, dropdown in (self.runtime.dropdowns or {}).items():

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

            for key in (
                    "Материал",
                    "материал",
            ):

                value = specs.get(key)

                if value:
                    raw_material = str(
                        value
                    ).strip().lower()

                    break

        if not raw_material:

            specs = (
                    card.get(
                        "specs",
                        {}
                    )
                    or {}
            )

            for key in (
                    "Состав",
                    "состав",
            ):

                value = specs.get(key)

                if value:
                    raw_material = str(
                        value
                    ).strip().lower()

                    break

        if not raw_material:
            return ""

        material = self._normalize_material(
            raw_material
        )
        print(
            "MATERIAL:",
            repr(raw_material),
            "->",
            repr(material)
        )
        return material
    # ==========================================================
    # MATERIAL NORMALIZATION
    # ==========================================================
    def _normalize_material(
            self,
            material
    ):
        material = str(
            material or ""
        ).strip().lower()

        if not material:
            return ""

        material = re.sub(
            r"\s+",
            " ",
            material
        )
        # --------------------------------------------------
        # MATERIALS WITH PERCENTAGES
        #
        # Например:
        # "вискоза 67%, полиэстер 33%"
        #
        # Берём только материал с максимальным процентом.
        # --------------------------------------------------
        matches = re.findall(
            r"(\d+(?:[.,]\d+)?)\s*%\s*([^,;]+)",
            material
        )

        if matches:

            parsed = []

            for percent, name in matches:

                try:
                    value = float(
                        percent.replace(
                            ",",
                            "."
                        )
                    )

                except ValueError:
                    continue

                name = re.sub(
                    r"\d+(?:[.,]\d+)?\s*%",
                    "",
                    name
                )
                name = name.strip(
                    " ,;.-"
                )
                if not name:
                    continue

                parsed.append(
                    (
                        value,
                        name
                    )
                )
            if parsed:
                parsed.sort(
                    key=lambda item: item[0],
                    reverse=True
                )
                # Только название материала.
                # Сам знак % и число сюда никогда не попадут.
                return parsed[0][1]

        # --------------------------------------------------
        # MATERIAL WITHOUT PERCENTAGES
        #
        # "кожа, велюр"
        # -> "кожа"
        #
        # "металл, пластик, дерево"
        # -> "металл"
        # --------------------------------------------------

        material = re.sub(
            r"\d+(?:[.,]\d+)?\s*%",
            "",
            material
        )

        parts = re.split(
            r"\s*[,;/]\s*",
            material
        )

        for part in parts:

            part = part.strip(
                " ,;.-"
            )

            if part:
                return part

        return material.strip(
            " ,;.-"
        )
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

        if not material:
            return

        known_materials = (
                product_info.get(
                    "material_codes",
                    {}
                )
                or {}
        )

        normalized_known = {
            str(key)
            .strip()
            .lower()
            for key in known_materials
        }

        if material in normalized_known:
            return

        report.new_material_codes.append(
            NewMaterialCode(
                product=product_name,
                material=material,
                code=code,
            )
        )

        print(
            "NEW MATERIAL:",
            product_name,
            material,
            code
        )
    # ==========================================================
    # ALIAS
    # ==========================================================
    def _add_alias(
            self,
            report,
            product,
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
    def _analyze_dropdown(self, report, description, product_name, code):

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

        dropdown = (self.runtime.get_dropdown(product_name))
        if not dropdown:
            dropdown = (self.runtime.get_dropdown(description))
        if not dropdown:
            return

        known_codes = {
            str(item.get("code", "")).strip()
            for item in (dropdown.get("variants", [])
                         or []
                         )
        }
        if code in known_codes:
            return
        for item in report.new_dropdown_variants:

            if (item.product == product_name and str(item.code).strip() == code):
                return

        report.new_dropdown_variants.append(
            NewDropdownVariant(product=product_name, code=code))
        print("NEW DROPDOWN:", product_name, code)
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

        if len(word) < 5:
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
        print("NEW MATERIALS:", len(report.new_material_codes))
        print("NEW DROPDOWNS:", len(report.new_dropdown_variants))
        print("NEW PATTERNS:", len(report.new_patterns))
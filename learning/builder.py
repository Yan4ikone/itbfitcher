from pathlib import Path
from pprint import pformat
import importlib

import dictionaries.products as products_dictionary
from dictionaries.products import PRODUCTS


class LearningBuilder:
    """
    ВАЖНО - ИСТОРИЯ ПРАВКИ:

    Раньше __init__ брал self.products = PRODUCTS - статичный снимок
    ВСЕГО словаря на момент старта сессии обучения. save_products()
    честно перечитывал products.py заново перед сохранением, но
    затем СЛИВАЛ (union) этот свежий диск со старым снимком
    self.products через _merge_products(). Если между стартом сессии
    и save() кто-то вручную удалил строку прямо в products.py, она
    всё ещё жила в старом снимке self.products - и union возвращал
    её обратно. Ручные удаления буквально "воскресали" при следующем
    обучении.

    Теперь LearningBuilder не хранит копию всего словаря вообще -
    только ДЕЛЬТУ: что конкретно нужно добавить (новые товары,
    алиасы, материалы, dropdown-варианты, паттерны). Полное состояние
    словаря читается с диска ОДИН РАЗ, непосредственно перед записью,
    и дельта применяется поверх него. Ручные правки, сделанные до
    этого момента, никогда не перезаписываются и не воскрешаются -
    мы просто не храним старую версию, с которой их можно было бы
    "слить".
    """

    def __init__(self):

        self._new_products = {}            # description -> info
        self._new_aliases = {}             # product -> set(alias)
        self._new_materials = {}           # product -> {material: code}
        self._new_dropdown_variants = {}   # product -> [variant, ...]
        self._dropdown_match_extensions = {}   # product -> {code: set(words)}
        self._new_dropdowns = {}           # product -> {"title":..., "variants": [...]}
        self._new_patterns = {}            # product -> set(pattern)

        # Только для чтения (например, LearningAnalyzer может
        # захотеть свериться с актуальным состоянием) - не участвует
        # в сохранении, чтобы не повторить старую ошибку.
        self.products = PRODUCTS
    # ==========================================================
    # PRODUCTS
    # ==========================================================
    def add_product(self, item):

        if item.description in self._new_products:
            return

        self._new_products[item.description] = {
            "code": str(item.code),
            "patterns": [],
            "aliases": [],
            "material_codes": {},
        }
    # ==========================================================
    # ALIASES
    # ==========================================================
    def add_alias(self, item):

        alias = str(item.alias).strip().lower()

        if not alias:
            return

        self._new_aliases.setdefault(item.product, set()).add(alias)
    # ==========================================================
    # MATERIALS
    # ==========================================================
    def add_material(self, item):

        material = str(item.material).strip().lower()

        if not material:
            return

        self._new_materials.setdefault(
            item.product,
            {}
        )[material] = str(item.code)
    # ==========================================================
    # DROPDOWNS (вариант к уже существующему dropdown)
    # ==========================================================
    def add_dropdown_variant(self, item):

        code = str(item.code).strip()

        if not code:
            return

        self._new_dropdown_variants.setdefault(
            item.product,
            []
        ).append({
            "code": code,
            "name": getattr(item, "name", "") or f"Вариант {code}",
            "group": getattr(item, "group", "") or "other",
            "match": list(getattr(item, "match", ()) or ()),
        })
    # ==========================================================
    # DROPDOWN MATCH WORDS (расширение УЖЕ существующего варианта)
    # ==========================================================
    def extend_dropdown_variant_match(self, item):

        code = str(item.code).strip()
        words = [str(w).strip().lower() for w in (item.words or ()) if str(w).strip()]

        if not code or not words:
            return

        self._dropdown_match_extensions.setdefault(
            item.product, {}
        ).setdefault(code, set()).update(words)
    # ==========================================================
    # DROPDOWN CANDIDATE -> НОВЫЙ DROPDOWN
    # ==========================================================
    def create_dropdown(self, item):
        """
        item - NewDropdownCandidate: product + codes (кортеж пар
        (код, count)) + keywords (кортеж пар (код, кортеж слов) -
        автоподсказка из learning.learning_filters.
        extract_dropdown_keywords). Заводит для товара блок
        "dropdown" с вариантами: name/match заполняются
        автоматически по накопленным словам, а не заглушкой
        "Авто N" - куратор донастраивает при необходимости прямо
        в окне обучения перед подтверждением.

        Если у товара к моменту save() уже появился dropdown -
        _apply_delta() ничего не перезапишет, чтобы не потерять
        уже настроенные name/group.
        """

        keywords_by_code = dict(getattr(item, "keywords", ()) or ())

        variants = []

        for index, (code, _count) in enumerate(item.codes, start=1):

            code = str(code).strip()

            if not code:
                continue

            words = tuple(keywords_by_code.get(code, ()))
            name = words[0].capitalize() if words else f"Авто {index}"

            variants.append({
                "code": code,
                "name": name,
                "group": "other",
                "match": list(words),
            })

        if not variants:
            return

        self._new_dropdowns[item.product] = {
            "title": "Выберите вариант",
            "variants": variants,
        }
    # ==========================================================
    # PATTERNS
    # ==========================================================
    def add_pattern(self, item):

        pattern = str(item.pattern).strip()

        if not pattern:
            return

        self._new_patterns.setdefault(item.product, set()).add(pattern)
    # ==========================================================
    # SAVE PRODUCTS
    # ==========================================================
    def save_products(self):

        path = (
            Path(__file__).parent.parent
            / "dictionaries"
            / "products.py"
        )
        importlib.invalidate_caches()
        fresh_module = importlib.reload(products_dictionary)

        # Единственный источник истины на момент сохранения - диск,
        # прочитанный ПРЯМО СЕЙЧАС. Дельта применяется поверх него.
        current = fresh_module.PRODUCTS

        self._apply_delta(current)

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:
            f.write("PRODUCTS = ")
            f.write(
                pformat(
                    current,
                    width=140,
                    sort_dicts=False
                )
            )

        self.products = current
    # ==========================================================
    # ПРИМЕНЕНИЕ ДЕЛЬТЫ
    # ==========================================================
    def _apply_delta(self, current):

        # 1. Новые товары - если такого описания ещё нет на диске.
        for description, info in self._new_products.items():
            current.setdefault(description, info)

        # 2. Алиасы - только к уже существующим на диске товарам.
        # Дедуп по нормализованному (регистр/пробелы) виду.
        for product, aliases in self._new_aliases.items():

            target = current.get(product)

            if not target:
                continue

            existing = target.setdefault("aliases", [])
            known = {
                str(value).strip().lower()
                for value in existing
            }

            for alias in aliases:

                if alias not in known:
                    existing.append(alias)
                    known.add(alias)

        # 3. Материалы.
        for product, materials in self._new_materials.items():

            target = current.get(product)

            if not target:
                continue

            target.setdefault("material_codes", {}).update(materials)

        # 4. Dropdown-варианты к уже существующему dropdown.
        for product, variants in self._new_dropdown_variants.items():

            target = current.get(product)

            if not target:
                continue

            dropdown = target.setdefault(
                "dropdown",
                {"title": "Выберите вариант", "variants": []}
            )
            existing_variants = dropdown.setdefault("variants", [])
            known_codes = {
                str(v.get("code", "")).strip()
                for v in existing_variants
            }

            for variant in variants:

                code = str(variant.get("code", "")).strip()

                if code and code not in known_codes:
                    existing_variants.append(variant)
                    known_codes.add(code)

        # 5. Новые dropdown целиком (товар раньше вообще без dropdown).
        for product, dropdown in self._new_dropdowns.items():

            target = current.get(product)

            if not target:
                continue

            if target.get("dropdown"):
                # Кто-то успел завести dropdown раньше нас (вручную
                # или в другой сессии) - не перезаписываем.
                continue

            target["dropdown"] = dropdown

        # 5.5. Расширение match у УЖЕ существующих dropdown-вариантов
        # словами, накопленными из новых подтверждённых карточек -
        # это и есть "расширение зонтика" без ручного набора текста.
        for product, by_code in self._dropdown_match_extensions.items():

            target = current.get(product)

            if not target:
                continue

            dropdown = target.get("dropdown") or {}
            variants = dropdown.get("variants", []) or []

            for variant in variants:

                code = str(variant.get("code", "")).strip()
                new_words = by_code.get(code)

                if not new_words:
                    continue

                existing = variant.setdefault("match", [])
                known = {str(w).strip().lower() for w in existing}

                for word in new_words:
                    if word not in known:
                        existing.append(word)
                        known.add(word)

        # 6. Паттерны.
        for product, patterns in self._new_patterns.items():

            target = current.get(product)

            if not target:
                continue

            existing = target.setdefault("patterns", [])

            for pattern in patterns:

                if pattern not in existing:
                    existing.append(pattern)
    # ==========================================================
    # SAVE
    # ==========================================================
    def save(self):

        self.save_products()
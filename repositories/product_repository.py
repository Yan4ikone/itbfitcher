from pathlib import Path
from pprint import pformat
import importlib

from dictionaries.dropdown_lists import DROPDOWN_LISTS
import dictionaries.products as products_dictionary


class ProductRepository:

    def __init__(self):
        self.products = products_dictionary.PRODUCTS

        # ----------------------------------------------------------
        # Индексы
        # ----------------------------------------------------------
        self.search_index = {}

        # token -> set(product)
        self.token_index = {}

        # alias token -> set(product)
        self.alias_token_index = {}

        # score word -> set(product)
        self.score_word_index = {}

        # Кэш токенов, чтобы не выполнять split/lower постоянно
        self.product_tokens = {}
        self.alias_tokens = {}

        self.rebuild_index()

    # ==============================================================
    # NORMALIZE / TOKENS
    # ==============================================================

    @staticmethod
    def _tokens(text):
        if not text:
            return set()

        return {
            word.lower()
            for word in str(text).split()
            if len(word) > 2
        }

    # ==============================================================
    # PRODUCTS
    # ==============================================================

    def all_products(self):
        return self.products.items()

    def all(self):
        return self.products.items()

    def reload(self):

        importlib.invalidate_caches()
        importlib.reload(products_dictionary)

        self.products = products_dictionary.PRODUCTS

        self.rebuild_index()

    # ==============================================================
    # INDEX
    # ==============================================================

    def rebuild_index(self):

        self.search_index = {}
        self.token_index = {}
        self.alias_token_index = {}
        self.score_word_index = {}

        self.product_tokens = {}
        self.alias_tokens = {}

        for product, info in self.products.items():

            code = str(info.get("code", ""))

            # ------------------------------------------------------
            # Exact search index
            # ------------------------------------------------------

            self.search_index[product.lower()] = {
                "product": product,
                "code": code,
            }

            # ------------------------------------------------------
            # Product tokens
            # ------------------------------------------------------

            product_tokens = self._tokens(product)

            self.product_tokens[product] = product_tokens

            for token in product_tokens:

                self.token_index.setdefault(
                    token,
                    set(),
                ).add(product)

            # ------------------------------------------------------
            # Aliases
            # ------------------------------------------------------

            for alias in info.get("aliases", []):

                alias_lower = str(alias).lower()

                self.search_index[alias_lower] = {
                    "product": product,
                    "code": code,
                }

                alias_tokens = self._tokens(alias)

                self.alias_tokens[
                    (product, alias)
                ] = alias_tokens

                for token in alias_tokens:

                    self.alias_token_index.setdefault(
                        token,
                        set(),
                    ).add(product)

            # ------------------------------------------------------
            # Score words
            # ------------------------------------------------------

            for word in info.get("score_words", []):

                word_lower = str(word).strip().lower()

                if not word_lower:
                    continue

                self.score_word_index.setdefault(
                    word_lower,
                    set(),
                ).add(product)

        print(
            "[ProductRepository] Индексы построены:",
            f"products={len(self.products)}",
            f"product_tokens={len(self.token_index)}",
            f"alias_tokens={len(self.alias_token_index)}",
            f"score_words={len(self.score_word_index)}",
        )

    # ==============================================================
    # FAST CANDIDATE SEARCH
    # ==============================================================

    def find_candidate_products(self, tokens):
        """
        Быстрый предварительный поиск товаров.

        Возвращает множество товаров, которые потенциально могут
        соответствовать хотя бы одному token карточки.

        ВАЖНО:
        Это только предварительный фильтр.
        Финальное решение по-прежнему принимает CandidateFinder
        и CandidateScorer.
        """

        if not tokens:
            return set()

        products = set()

        for token in tokens:

            token = token.lower()

            products.update(
                self.token_index.get(token, ())
            )

            products.update(
                self.alias_token_index.get(token, ())
            )

            products.update(
                self.score_word_index.get(token, ())
            )

        return products

    # ==============================================================
    # MODIFICATION
    # ==============================================================

    def add_alias(self, product, alias):

        info = self.get(product)

        if not info:
            return

        aliases = info.setdefault("aliases", [])

        if alias not in aliases:
            aliases.append(alias)

        self.rebuild_index()

    def add_score_word(self, product, word):

        info = self.get(product)

        if not info:
            return

        score_words = info.setdefault("score_words", [])

        if word not in score_words:
            score_words.append(word)
            self.rebuild_index()

    def add_material_code(self, product, material, code):

        info = self.get(product)

        if not info:
            return

        material_codes = info.setdefault(
            "material_codes",
            {}
        )

        material_codes[material] = code

    def add(self, product, info):

        self.products[product] = info
        self.rebuild_index()

    def update(self, product, info):

        self.products[product] = info
        self.rebuild_index()

    def remove(self, product):

        if product in self.products:
            del self.products[product]

        self.rebuild_index()

    # ==============================================================
    # EXACT SEARCH
    # ==============================================================

    def find_product(self, description):

        if not description:
            return None

        return self.search_index.get(
            description.strip().lower()
        )

    # ==============================================================
    # DROPDOWN
    # ==============================================================

    def find_dropdown(self, description):

        description = (description or "").lower()

        for product, dropdown in DROPDOWN_LISTS.items():

            if product.lower() in description:
                return dropdown

        return None

    # ==============================================================
    # GETTERS
    # ==============================================================

    def get(self, product):
        return self.products.get(product)

    def has(self, product):
        return product in self.products

    def get_default_code(self, product):

        info = self.get(product)

        if not info:
            return ""

        return info.get("code", "")

    def get_material_code(self, product, material):

        info = self.get(product)

        if not info:
            return ""

        return info.get(
            "material_codes",
            {}
        ).get(
            material.lower(),
            ""
        )

    def get_material_codes(self, product):

        info = self.get(product)

        if not info:
            return {}

        return info.get(
            "material_codes",
            {}
        )

    def get_aliases(self, product):

        info = self.get(product)

        if not info:
            return []

        return info.get(
            "aliases",
            []
        )

    def get_patterns(self, product):

        info = self.get(product)

        if not info:
            return []

        return info.get(
            "patterns",
            []
        )

    def get_score_words(self, product):

        info = self.get(product)

        if not info:
            return []

        return info.get(
            "score_words",
            []
        )

    def get_display_name(self, product):

        if isinstance(product, list):

            if not product:
                return ""

            product = product[0]

        if not isinstance(product, str):
            product = str(product)

        info = self.get(product)

        if not info:
            return product.capitalize()

        return info.get(
            "display_name",
            product.capitalize()
        )

    # ==============================================================
    # SAVE
    # ==============================================================

    def save(self):

        path = (
            Path(__file__).parent.parent
            / "dictionaries"
            / "products.py"
        )

        with open(
            path,
            "w",
            encoding="utf-8",
        ) as f:

            f.write("PRODUCTS = ")
            f.write(
                pformat(
                    self.products,
                    width=140,
                    sort_dicts=False,
                )
            )
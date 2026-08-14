from pprint import pformat

from dictionaries.dropdown_lists import DROPDOWN_LISTS
from learning.pending import load_pending_products, PENDING_PRODUCTS
from modules.learning_filter import is_good_alias


class Trainer:

    def __init__(self, repository):
        self.repository = repository

    def learn(self, card, result, corrected_description, corrected_code, corrected_material=""):

        corrected_description = (corrected_description or "").strip().lower()
        corrected_code = str(corrected_code or "").strip()
        corrected_material = (corrected_material or "").strip().lower()

        if not corrected_description:
            return

        if not self.repository.has(corrected_description):

            self.add_product(corrected_description, corrected_code)
            return

        if card:
            original = (card.title or "").strip().lower()

            if original and original != corrected_description:
                self.learn_alias(corrected_description, original)

        if corrected_material:
            self.repository.add_material_code(
                corrected_description,
                corrected_material,
                corrected_code
            )

        default_code = self.repository.get_default_code(corrected_description)

        if default_code and default_code != corrected_code:
            self.add_dropdown(corrected_description)
        self.repository.save()

    def learn_alias(self, product, alias):

        alias = (alias or "").strip().lower()

        if not is_good_alias(alias):
            return

        self.repository.add_alias(product, alias)


    def learn_word(self, product, word):

        word = (word or "").strip().lower()

        if len(word) < 4:
            return

        if any(ch.isdigit() for ch in word):
            return

        self.repository.add_score_word(product, word)


    def apply_pending_products(self, min_count=3):

        changed = False
        pending = load_pending_products()

        for product, info in pending.items():

            if info.get("count", 0) < min_count:
                continue

            if not self.repository.has(product):

                self.repository.add(
                    product,
                    {
                        "display_name": info.get(
                            "display_name",
                            product.capitalize()
                        ),
                        "code": info.get("code", ""),
                        "aliases": [],
                        "patterns": [],
                        "score_words": [],
                        "material_codes": dict(
                            info.get("materials", {})
                        )
                    }
                )

                changed = True

            else:

                for material, code in info.get(
                        "materials",
                        {}
                ).items():

                    self.repository.add_material_code(
                        product,
                        material,
                        code
                    )

                changed = True

            del PENDING_PRODUCTS[product]

        if not changed:
            return False

        self.repository.save()

        return True

    def add_product(self, description, code, display_name=None):

        description = (
            description
            .strip()
            .lower()
        )

        if self.repository.has(description):
            return False

        self.repository.add(
            description,
            {
                "display_name":
                    display_name
                    or
                    description.capitalize(),
                "code": str(code),
                "aliases": [],
                "patterns": [],
                "score_words": [],
                "material_codes": {}
            }
        )

        self.repository.mark_dirty()

        return True

    def add_dropdown(self, description):

        description = description.lower()

        if description in DROPDOWN_LISTS:
            return False

        DROPDOWN_LISTS[description] = {
            "title": "Выберите вариант",
            "variants": []
        }

        self.save_dropdowns()
        return True

    def save_dropdowns(self):

        with open(
                "dictionaries/dropdown_lists.py",
                "w",
                encoding="utf-8"
        ) as f:

            f.write("DROPDOWN_LISTS = ")
            f.write(
                pformat(
                    DROPDOWN_LISTS,
                    width=140,
                    sort_dicts=False
                )
            )
    def apply_analysis(self, report):

        changed = False
        # ---------- Новые товары ----------
        for item in report.get("new_products", []):

            if self.add_product(
                    description=item["description"],
                    code=item["code"],
                    display_name=item["description"].capitalize()
            ):
                changed = True
        # ---------- Алиасы ----------
        for item in report.get("new_aliases", []):

            self.learn_alias(item["product"], item["alias"])
            changed = True
        # ---------- Материалы ----------
        for item in report.get("new_material_codes", []):

            self.repository.add_material_code(
                item["product"],
                item["material"],
                item["code"]
            )
            changed = True
        # ---------- Новые dropdown ----------
        for item in report.get("new_dropdowns", []):
            self.add_dropdown(item["product"])
            changed = True
        # ---------- Новые варианты dropdown ----------
        for item in report.get("new_dropdown_variants", []):

            dropdown = DROPDOWN_LISTS.setdefault(
                item["product"],
                {
                    "title": "Выберите вариант",
                    "variants": []
                }
            )
            exists = any(
                v["code"] == item["code"]
                for v in dropdown["variants"]
            )
            if not exists:
                dropdown["variants"].append(
                    {
                        "code": item["code"],
                        "name": "Авто",
                        "group": "other"
                    }
                )
                changed = True
        if changed:
            self.repository.save()
            self.save_dropdowns()
        return changed
import json
from pathlib import Path

from repositories.card_repository import CardRepository

LEARNING_FILE = Path("learning/manual_learning.json")


class LearningRepository:

    def __init__(self):
        self.data = self.load()
        print("LearningRepository:", id(self))

    def load(self):

        if not LEARNING_FILE.exists():
            return {
                "manual": {},
                "products": {},
                "dropdowns": {},
                "materials": {},
                "pending": {}
            }

        with open(
                LEARNING_FILE,
                "r",
                encoding="utf-8"
        ) as f:
            return json.load(f)

    def save(self):

        LEARNING_FILE.parent.mkdir(exist_ok=True)

        with open(
                LEARNING_FILE,
                "w",
                encoding="utf-8"
        ) as f:

            json.dump(
                self.data,
                f,
                ensure_ascii=False,
                indent=2
            )
    # ==========================================================
    # Runtime API
    # ==========================================================
    def load_manual(self):
        return self.data.setdefault("manual", {})

    def load_products(self):
        return self.data.setdefault("products", {})

    def load_cards(self):
        repository = CardRepository()
        return repository.data
    # ==========================================================
    # Manual
    # ==========================================================
    def remember_manual(self, url, description, code, material=""):

        self.data.setdefault("manual", {})[url] = {
            "description": description,
            "code": code,
            "material": material,
            "approved": True
        }
        print(
            "SAVE",
            id(self),
            url,
            len(self.data["manual"])
        )
        self.save()
    # ==========================================================
    # Products
    # ==========================================================
    def has_product(self, product):

        return product in self.data.setdefault(
            "products",
            {}
        )
    def get_product(self, product):

        return self.data.setdefault(
            "products",
            {}
        ).get(product, {})

    def add_product(self, product, info):

        self.data.setdefault(
            "products",
            {}
        )[product] = info

        self.save()
    # ==========================================================
    # Dropdowns
    # ==========================================================
    def get_dropdown(self, product):

        return self.data.setdefault(
            "dropdowns",
            {}
        ).get(product)

    def add_dropdown(self, product, dropdown):

        self.data.setdefault(
            "dropdowns",
            {}
        )[product] = dropdown

        self.save()
    # ==========================================================
    # Materials
    # ==========================================================
    def get_materials(self, product):

        return self.data.setdefault(
            "materials",
            {}
        ).get(product, {})

    def set_materials(self, product, materials):

        self.data.setdefault(
            "materials",
            {}
        )[product] = materials

        self.save()
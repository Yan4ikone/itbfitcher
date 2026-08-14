from learning.analyzer import LearningAnalyzer
from learning.repository import LearningRepository
from repositories.card_repository import CardRepository
from repositories.product_repository import ProductRepository


class LearningRuntime:

    def __init__(self):

        self.repository = LearningRepository()
        self.cards = CardRepository()
        self.product_repository = ProductRepository()
        self.reload()

    def reload(self):

        self.manual = self.repository.load_manual()
        self.dropdowns = self.repository.load_dropdowns()
        self.materials = self.repository.load_materials()
        self.pending = self.repository.get_pending()

    def refresh(self):
        self.reload()

    # ==========================================================
    # LEARNING PROCESSED
    # ==========================================================

    def is_learning_processed(self, url):

        card = self.cards.data.get(url)

        if not card:
            return False
        return bool(card.get("learning_processed", False))

    def mark_learning_processed(self, urls):

        changed = False

        for url in urls:
            if not url:
                continue

            card = self.cards.data.get(url)

            if not card:
                continue
            if card.get("learning_processed"):
                continue

            card["learning_processed"] = True
            changed = True

        if changed:
            self.cards.mark_dirty()
            self.cards.flush()

    # ==========================================================

    def find_manual(self, card):
        return self.get_manual(card.url)

    def get_manual(self, url):
        return self.manual.get(url)

    def all_products(self):
        return self.product_repository.all()

    def get_product(self, name):
        return self.product_repository.get(name)

    def has_product(self, name):
        return self.product_repository.has(name)

    def get_dropdown(self, product):
        return self.dropdowns.get(product)

    def get_materials(self, product):
        return self.materials.get(product, {})

    def analyze(self):
        return LearningAnalyzer(self).analyze()

    def all_cards(self):

        cards = self.cards.data

        print("CARDS COUNT:", len(cards))
        print("RUNTIME FILE:", self.cards.file.resolve())
        print("RUNTIME EXISTS:", self.cards.file.exists())

        for url in cards:
            print("CARD IN DB:", url)

        return cards.values()
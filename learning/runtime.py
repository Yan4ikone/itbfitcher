from learning.analyzer import LearningAnalyzer
from learning.repository import LearningRepository
from repositories.card_repository import CardRepository


class LearningRuntime:

    def __init__(self):

        self.repository = LearningRepository()
        self.cards = CardRepository()
        self.reload()

    def reload(self):

        self.manual = self.repository.load_manual()
        self.products = self.repository.load_products()
        self.dropdowns = self.repository.load_dropdowns()
        self.materials = self.repository.load_materials()
        self.pending = self.repository.get_pending()

    def refresh(self):
        self.reload()

    def find_manual(self, card):
        return self.manual.get(card.url)

    def all_products(self):
        return self.products.items()

    def get_product(self, name):
        return self.products.get(name)

    def get_dropdown(self, product):
        return self.dropdowns.get(product)

    def get_materials(self, product):
        return self.materials.get(product, {})

    def analyze(self):
        return LearningAnalyzer(self).analyze()

    def all_cards(self):
        return self.repository.load_cards().values()
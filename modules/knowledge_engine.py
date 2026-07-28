from learning.runtime import LearningRuntime
from repositories.card_repository import CardRepository
from repositories.product_repository import ProductRepository


class KnowledgeEngine:

    def __init__(self):

        self.product_repository = ProductRepository()
        self.learning = LearningRuntime()
        self.card_repository = CardRepository()

    def refresh_learning(self):
        self.learning.refresh()

    def find_manual(self, card):
        return self.learning.find_manual(card)

    def get_manual(self, url):
        return self.learning.get_manual(url)

    def analyze_learning(self):
        return self.learning.analyze()

    def find_card(self, card):
        return self.card_repository.find(card)

    def find_product(self, description):
        return self.product_repository.find_product(description)

    def all_products(self):
        return self.product_repository.all_products()

    def has_product(self, product):
        return self.product_repository.has(product)

    def get_product(self, product):
        return self.product_repository.get(product)

    def get_default_code(self, product):
        return self.product_repository.get_default_code(product)

    def get_material_code(self, product, material):
        return self.product_repository.get_material_code(product, material)

    def get_material_codes(self, product):
        return self.product_repository.get_material_codes(product)

    def get_aliases(self, product):
        return self.product_repository.get_aliases(product)

    def get_patterns(self, product):
        return self.product_repository.get_patterns(product)

    def get_score_words(self, product):
        return self.product_repository.get_score_words(product)

    def get_display_name(self, product):
        return self.product_repository.get_display_name(product)

    def find_dropdown(self, description):
        return self.product_repository.find_dropdown(description)
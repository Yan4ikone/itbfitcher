from learning.analyzer import LearningAnalyzer
from learning.learning_filters import extract_manual_description, extract_manual_code
from learning.repository import LearningRepository
from repositories.card_archiver import archive_full_cards
from repositories.card_repository import CardRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from repositories.product_repository import ProductRepository


class LearningRuntime:

    def __init__(self):

        self.repository = LearningRepository()
        self.cards = CardRepository()
        self.knowledge_base = KnowledgeBaseRepository()
        self.product_repository = ProductRepository()
        self.reload()

    def reload(self):

        self.manual = self.repository.load_manual()

    def refresh(self):
        self.reload()
    # ==========================================================
    # LEARNING PROCESSED
    # ==========================================================
    def is_learning_processed(self, url):

        # Карточка, уже попавшая в лёгкую базу знаний, точно прошла
        # обучение (это единственное место, которое её туда кладёт) -
        # её полной версии в self.cards.data больше нет вообще, она
        # заархивирована, поэтому этот случай проверяем отдельно.
        if self.knowledge_base.has(url):
            return True

        card = self.cards.data.get(url)

        if not card:
            return False
        return bool(card.get("learning_processed", False))

    def mark_learning_processed(self, urls):
        """

        Теперь для каждой карточки, прошедшей обучение:
        1. Лёгкая версия (url, ИСПРАВЛЕННОЕ куратором наименование,
           ИСПРАВЛЕННЫЙ код) уходит в storage/knowledge_base.json -
           остаётся навсегда, дёшево читать, этого достаточно для
           кэша классификации по URL.
        2. Полная версия архивируется (repositories/card_archiver.py -
           сейчас локально, задел под отправку в облако).
        3. Полная версия убирается из runtime_cards.json совсем
           (CardRepository.forget), чтобы файл не разрастался.

        """

        to_archive = {}
        changed = False

        for url in urls:

            if not url:
                continue

            if self.knowledge_base.has(url):
                # Уже заархивирована в прошлый раз - нечего делать.
                continue

            card = self.cards.data.get(url)

            if not card:
                continue

            manual = self.manual.get(card.get("normalized_url", url))

            if manual:

                description = extract_manual_description(manual)
                code = extract_manual_code(manual)

            else:

                description = (
                    card.get("display_name")
                    or card.get("product")
                    or card.get("description", "")
                )
                code = card.get("code", "")

            if not description or not code:
                # Ни исправленного, ни автоматического значения нет -
                # архивировать нечего, оставляем карточку как есть на
                # следующий раз.
                continue

            self.knowledge_base.remember(
                url=url,
                product=description,
                code=code,
            )

            to_archive[url] = dict(card)
            self.cards.forget(url)
            changed = True

        if to_archive:
            archive_full_cards(to_archive)
            self.knowledge_base.flush()

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
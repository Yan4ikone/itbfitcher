from utils.json_repository import JsonRepository


class KnowledgeBaseRepository(JsonRepository):
    """
    Лёгкая "база знаний": url -> {"product": ..., "code": ...}.

    В отличие от storage/runtime_cards.json (репозиторий ПОЛНЫХ
    карточек - specs, images, sections, breadcrumbs и т.п., нужный
    для кэша классификации и как сырьё для LearningAnalyzer ПОКА
    карточка не прошла обучение), эта база хранит только то, что
    реально нужно помнить НАВСЕГДА после того, как карточка прошла
    обучение: подтверждённое куратором название и код ТН ВЭД.

    Ключ "product" (а не "description") выбран намеренно - именно
    его читает classifier/card_classifier.py::CardClassifier.apply()
    при кэш-хите (history.get("product")). Раньше ключ назывался
    "description" и не совпадал с тем, что реально читалось - кэш
    молча ничего не подхватывал.

    Как только карточка отмечена learning_processed (см.
    learning/runtime.py::mark_learning_processed), её лёгкая версия
    попадает сюда - причём ИСПРАВЛЕННАЯ куратором версия
    (manual_learning.json["manual"]), а не результат первоначальной
    автоклассификации. Полная версия карточки архивируется отдельно
    (repositories/card_archiver.py) и удаляется из runtime_cards.json.
    """

    def __init__(self):
        super().__init__("storage/knowledge_base.json")

    def remember(self, url, product, code):

        if not url:
            return

        self.data[url] = {
            "product": product,
            "code": code,
        }
        self.mark_dirty()

    def get(self, url):
        return self.data.get(url)

    def has(self, url):
        return url in self.data

    def all(self):
        return self.data.items()
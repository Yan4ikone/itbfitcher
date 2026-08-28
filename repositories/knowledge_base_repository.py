from utils.json_repository import JsonRepository


class KnowledgeBaseRepository(JsonRepository):
    """
    Лёгкая "база знаний": url -> {"description": ..., "code": ...}.

    В отличие от storage/runtime_cards.json (репозиторий ПОЛНЫХ
    карточек - specs, images, sections, breadcrumbs и т.п., нужный
    для кэша классификации и как сырьё для LearningAnalyzer ПОКА
    карточка не прошла обучение), эта база хранит только то, что
    реально нужно помнить НАВСЕГДА после того, как карточка прошла
    обучение: подтверждённое название и код ТН ВЭД.

    Как только карточка отмечена learning_processed (см.
    learning/runtime.py::mark_learning_processed), её лёгкая версия
    попадает сюда, а полная версия архивируется отдельно
    (repositories/card_archiver.py) и удаляется из runtime_cards.json -
    иначе этот файл растёт без пользы бесконечно.
    """

    def __init__(self):
        super().__init__("storage/knowledge_base.json")

    def remember(self, url, description, code):

        if not url:
            return

        self.data[url] = {
            "description": description,
            "code": code,
        }
        self.mark_dirty()

    def get(self, url):
        return self.data.get(url)

    def has(self, url):
        return url in self.data

    def all(self):
        return self.data.items()
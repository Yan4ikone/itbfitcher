import pandas as pd

from learning.repository import LearningRepository
from repositories.card_repository import CardRepository
from repositories.knowledge_base_repository import KnowledgeBaseRepository
from repositories.product_repository import ProductRepository
from utils.url_utils import normalize_ozon_url


class ManualTeacher:

    def __init__(self):
        self.repository = LearningRepository()
        self.product_repository = ProductRepository()
        self.card_repository = CardRepository()
        self.knowledge_base = KnowledgeBaseRepository()

    def learn_result_file(self, path):
        df = pd.read_excel(path)
        statistics = {
            "manual_saved": 0,
            "new_products": 0,
            "dropdown_candidates": 0,
            "aliases": 0,
            "words": 0,
            # Сколько правок ушло НАПРЯМУЮ в storage/knowledge_base.json
            # в обход LearningAnalyzer - см. _refresh_knowledge_base_cache
            # ниже. Это карточки, которые уже прошли обучение раньше
            # (learning/runtime.py::mark_learning_processed заархивировал
            # их и убрал из runtime_cards.json) - LearningAnalyzer их
            # больше не увидит никогда (is_learning_processed вернёт
            # True), поэтому без этого прямого пути повторная правка
            # такой карточки молча терялась: куратор мог сколько угодно
            # раз чинить одно и то же наименование в Excel и жать
            # "Обучить" - ни словарь, ни (что хуже) кэш классификации
            # эту правку так и не увидят, и при следующей обработке того
            # же товара снова вернётся старое (неверное) значение из
            # кэша.
            "cache_refreshed": 0,
        }
        for _, row in df.iterrows():
            description = self._value(row, ["Описание", "описание"])
            code = self._value(row,["Тнвэд", "ТНВЭД", "Код"])
            url = self._value(row,["Ссылка", "URL"])
            if not description:
                continue
            if url:
                self.repository.remember_manual(
                    url=normalize_ozon_url(url),
                    description=description,
                    code=code
                )
                card = self.card_repository.find_by_url(url)

                if not card:
                    card = self.card_repository.find_by_normalized_url(url)
                if card:
                    card["manual_description"] = description
                    card["manual_code"] = code
                    self.card_repository.mark_dirty()
                else:
                    # Полной карточки уже нет в runtime_cards.json - она
                    # уже прошла обучение раньше и была заархивирована.
                    # LearningAnalyzer эту правку не увидит (см.
                    # learning/runtime.py::is_learning_processed), поэтому
                    # обновляем "лёгкую" запись в knowledge_base.json
                    # НАПРЯМУЮ - это и есть то самое место, которое
                    # реально читает двухуровневый кэш классификации
                    # (processors/ozon_auto_processor.py::get_cached_card)
                    # на каждой следующей обработке этого URL.
                    if self._refresh_knowledge_base_cache(url, description, code):
                        statistics["cache_refreshed"] += 1
                statistics["manual_saved"] += 1
            product = description.lower().strip()
            existing = self.repository.get_product(product)

            if not existing:
                statistics["new_products"] += 1
        self.repository.save()
        self.card_repository.flush()

        return statistics
    # ==========================================================
    # KNOWLEDGE BASE CACHE REFRESH
    # ==========================================================
    def _refresh_knowledge_base_cache(self, url, description, code):
        """
        Обновляет storage/knowledge_base.json НАПРЯМУЮ для карточки,
        которая уже прошла обучение раньше (её полной версии в
        runtime_cards.json больше нет) - если сохранённое там значение
        отличается от того, что куратор только что вписал в Excel.

        Пробуем И "сырой" URL как он есть в Excel, И нормализованный -
        knowledge_base.json исторически ключуется тем URL, который был
        в card.url на момент mark_learning_processed (обычно "сырой",
        как его вернул парсер), а не normalize_ozon_url().
        """

        if not code:
            return False

        candidates = [url]
        normalized = normalize_ozon_url(url)

        if normalized and normalized not in candidates:
            candidates.append(normalized)

        for candidate in candidates:

            existing = self.knowledge_base.get(candidate)

            if not existing:
                continue

            if (
                str(existing.get("product", "")).strip() == str(description).strip()
                and str(existing.get("code", "")).strip() == str(code).strip()
            ):
                return False

            self.knowledge_base.remember(
                url=candidate,
                product=description,
                code=code,
            )
            self.knowledge_base.flush()

            return True

        return False


    def _value(self, row, names):
        for name in names:
            if name not in row:
                continue
            value = row[name]
            if pd.isna(value):
                return ""
            if isinstance(value, float):
                if value.is_integer():
                    return str(int(value))
            return str(value).strip()
        return ""
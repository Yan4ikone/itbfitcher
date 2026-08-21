import pandas as pd

from learning.repository import LearningRepository
from learning.trainer import Trainer
from learning.pending import save_pending_products
from repositories.card_repository import CardRepository
from repositories.product_repository import ProductRepository
from utils.url_utils import normalize_ozon_url


class ManualTeacher:

    def __init__(self):
        self.repository = LearningRepository()
        self.product_repository = ProductRepository()
        self.trainer = Trainer(self.product_repository)
        self.card_repository = CardRepository()

    def learn_result_file(self, path):
        df = pd.read_excel(path)
        statistics = {
            "manual_saved": 0,
            "new_products": 0,
            "dropdown_candidates": 0,
            "aliases": 0,
            "words": 0
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
                statistics["manual_saved"] += 1
            product = description.lower().strip()
            existing = self.repository.get_product(product)

            if not existing:
                self._add_pending(product, description, code)
                statistics["new_products"] += 1
        self.repository.save()
        self.card_repository.flush()

        return statistics

    def _add_pending(self, product, description, code):
        pending = (self.repository .get_pending())
        item = pending.setdefault(
            product,
            {
                "display_name": description,
                "count": 0,
                "code": code,
                "materials": {}
            }
        )
        item["count"] += 1
        save_pending_products(pending)

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
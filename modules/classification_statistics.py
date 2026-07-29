from collections import Counter
import pandas as pd
import os


class ClassificationStatistics:

    def __init__(self):
        self.total = 0
        self.found = 0
        self.not_found = 0
        self.review = 0
        self.sources = Counter()
        self.material_found = 0
        self.material_missing = 0
        self.unknown_products = []
        self.rows = []

    def add(self, result):

        self.total += 1

        if result.code and result.code != "0":
            self.found += 1
        else:
            self.not_found += 1

        if result.review:
            self.review += 1

        if result.source:
            self.sources[result.source] += 1

        if result.material:
            self.material_found += 1
        else:
            self.material_missing += 1

        if result.source == "NOT_FOUND":
            self.unknown_products.append(result.normalized_name)

        self.rows.append({
            "Исходное": result.original_name,
            "Нормализовано": result.normalized_name,
            "Товар": result.product,
            "Материал": result.material,
            "Код": result.code,
            "Источник": result.source,
            "Проверка": result.review
        })

    def print_summary(self, logger=print):

        logger("")
        logger("=" * 60)
        logger("СТАТИСТИКА КЛАССИФИКАЦИИ")
        logger("=" * 60)
        logger(f"Всего строк: {self.total}")
        logger(f"Найдено автоматически: {self.found}")
        logger(f"Не найдено: {self.not_found}")
        logger(f"Ручная проверка: {self.review}")
        logger("")
        logger("Источники определения:")

        for source, count in sorted(self.sources.items()):
            logger(f"  {source}: {count}")
        logger("")
        logger(f"Материал найден: {self.material_found}")
        logger(f"Материал не найден: {self.material_missing}")

    def save_excel(self, input_path):

        folder = os.path.dirname(input_path)
        path = os.path.join(folder, "CLASSIFICATION_REPORT.xlsx")
        df = pd.DataFrame(self.rows)
        df.to_excel(path, index=False)

        return path
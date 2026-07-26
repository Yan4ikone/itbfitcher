from pathlib import Path
from datetime import datetime


class DecisionLogger:

    def __init__(self):

        self.folder = Path("logs")
        self.folder.mkdir(exist_ok=True)

    def save(self, card, result):

        filename = (
            datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            + ".txt"
        )

        path = self.folder / filename

        with open(path, "w", encoding="utf-8") as f:

            f.write("=" * 80 + "\n")
            f.write("КАРТОЧКА ТОВАРА\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"URL:\n{card.url}\n\n")

            f.write(f"Название:\n{card.title}\n\n")

            f.write(f"Описание:\n{card.description}\n\n")

            f.write("Характеристики\n")

            for key, value in card.specs.items():
                f.write(f"    {key}: {value}\n")

            f.write("\n")
            f.write("=" * 80 + "\n")
            f.write("РЕЗУЛЬТАТ\n")
            f.write("=" * 80 + "\n\n")

            f.write("=" * 80 + "\n")
            f.write("КАНДИДАТЫ PRODUCTS\n")
            f.write("=" * 80 + "\n\n")

            for candidate in result.product_scores:

                f.write(f"{candidate['product']}\n")
                f.write(f"score = {candidate['score']}\n")

                if "diff" in candidate:
                    f.write(f"diff = {candidate['diff']}\n")

                f.write("Совпадения:\n")

                f.write("Разбивка баллов:\n")

                for key, value in candidate["breakdown"].items():

                    if value:
                        f.write(f"    {key:15} +{value}\n")

                f.write("\nСовпадения:\n")

                for match in candidate["matches"]:
                    f.write(
                        f"    +{match['points']:3} "
                        f"{match['type']:15} "
                        f"{match['text']}\n"
                    )

                f.write(f"\nИТОГО: {candidate['score']}\n")

                f.write("\n")

            f.write(f"Товар: {result.product}\n")
            f.write(f"Материал: {result.material}\n")
            f.write(f"Код: {result.code}\n")
            f.write(f"Источник: {result.source}\n")
            f.write(f"Уверенность: {result.confidence}\n")
            f.write(f"Проверка: {result.review}\n\n")

            f.write("=" * 80 + "\n")
            f.write("TRACE\n")
            f.write("=" * 80 + "\n\n")
            f.write(result.trace.to_text())
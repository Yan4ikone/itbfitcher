"""
Точка расширения: сюда уходят ПОЛНЫЕ карточки (specs, images,
sections, breadcrumbs и т.п.) после того, как они прошли обучение и
их лёгкая версия (url/описание/код) уже сохранена в
storage/knowledge_base.json.

СЕЙЧАС: складывает карточки локальным JSON-архивом
(storage/cards_archive/<дата-время>.json), чтобы при отладке ничего
не терялось, пока реальная отправка "в облако" не подключена.

КОГДА появится конкретное хранилище (S3, свой API, Google Drive,
что угодно) - меняется ТОЛЬКО функция archive_full_cards() ниже,
вызывающий код (learning/runtime.py::mark_learning_processed) трогать
не придётся.
"""
import json
from datetime import datetime
from pathlib import Path


ARCHIVE_DIR = Path("storage/cards_archive")


def archive_full_cards(cards: dict) -> Path | None:
    """
    cards: {url: {...полная запись, как она лежала в
    storage/runtime_cards.json...}}

    Возвращает путь к файлу архива либо None, если cards пуст.
    """

    if not cards:
        return None

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    filename = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".json"
    path = ARCHIVE_DIR / filename

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            cards,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"[ARCHIVE] {len(cards)} карточек сохранено локально: {path}"
    )
    print(
        "[ARCHIVE] TODO: заменить на реальную отправку в облако "
        "(S3 / свой API / Google Drive - что решите использовать)"
    )

    return path
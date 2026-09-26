import logging

from PIL import Image
from io import BytesIO
import requests

log = logging.getLogger(__name__)


class ImageLoader:


    def __init__(self):
        self.timeout = 10

    def load_from_url(self, url):
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))

            return image.convert("RGB")
        except Exception as e:
            print(f"IMAGE LOAD ERROR: {e}")
            # ДОБАВЛЕНО (2026-09-26, products-dict-gradation-audit.md,
            # обновление 17) - тот же класс проблемы, что и в
            # processors/card_image_processor.py (см. комментарий там):
            # эта ошибка (картинка не загрузилась - истёкшая ссылка,
            # 403/404 от CDN, таймаут и т.п.) - ОДНА из самых вероятных
            # причин, почему ИИ-фоллбек в decision_engine.py (шаг 7.5)
            # молча ничего не находит (card.image_description остаётся
            # пустой - см. новую ветку IMAGE_FALLBACK_EMPTY там), а
            # раньше была видна ТОЛЬКО через print(), невидимый в
            # дочернем процессе classifier-пула / windowed-сборке.
            log.warning("IMAGE LOAD ERROR: %s", e)
            return None
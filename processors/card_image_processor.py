import logging

from services.image_loader import ImageLoader
from utils.wb_image_resolver import resolve_wb_image_url

log = logging.getLogger(__name__)


class CardImageProcessor:


    def __init__(self, image_service):
        self.image_service = image_service
        self.image_loader = ImageLoader()



    def process(self, card):
        if not card.images:
            # ДОБАВЛЕНО: раньше здесь был безусловный `return card` -
            # для Wildberries card.images ВСЕГДА пуст (WB API не
            # отдаёт прямых ссылок на фото так, как это делает Ozon),
            # из-за чего ИИ-фоллбек (decision_engine.py, шаг 7.5)
            # молча ничего не делал вообще ни для одного WB-товара -
            # ни строчки в логе, ни ошибки (см. подробное объяснение
            # в utils/wb_image_resolver.py). card.url_product_id -
            # это nm_id товара, который card_builder.py заполняет
            # ТОЛЬКО для WB (см. models/card_builder.py) - пробуем
            # подобрать по нему URL картинки на CDN WB. Если это не
            # WB-карточка (url_product_id пуст) или подобрать не
            # удалось - ведём себя ровно как раньше.
            if not getattr(card, "url_product_id", ""):
                return card
            image_url = resolve_wb_image_url(card.url_product_id)
            if not image_url:
                return card
            card.images = [image_url]
        try:

            image = self.image_loader.load_from_url(
                card.images[0]
            )
            if image is None:
                return card


            description = (
                self.image_service.describe_images(
                    [image]
                )
            )
            if description:
                card.image_description = description
                if card.cleaned_text:
                    card.cleaned_text += (
                        " "
                        + description
                    )
                else:
                    card.cleaned_text = description
        except Exception as e:
            print(f"IMAGE PROCESS ERROR: {e}")
            # ДОБАВЛЕНО (2026-09-26, products-dict-gradation-audit.md,
            # обновление 17): раньше исключение здесь (не загрузилась
            # картинка, упал ИИ-запрос и т.п.) уходило ТОЛЬКО в print() -
            # а этот метод вызывается ИСКЛЮЧИТЕЛЬНО из decision_engine.py
            # шаг 7.5, который в боевом режиме почти всегда выполняется
            # внутри дочернего процесса classifier-пула
            # (processors/ozon_auto_processor.py::CLASSIFIER_WORKERS) -
            # там print() физически не может попасть ни в консоль, ни в
            # GUI-лог главного процесса (см. подробное объяснение в
            # utils/app_logging.py). Разбор кейса Яна "валик" (карточка
            # осталась "под вопросом", а куратор не мог понять, пробовал
            # ли вообще подключиться ИИ) показал, что это ЕДИНСТВЕННОЕ
            # место во всём ИИ-фоллбеке, которое всё ещё не дублировалось
            # в файл - в отличие от ошибки инициализации image_processor
            # (engines/decision_engine.py) и ошибок самого API
            # (engines/image_description_engine.py), которые такую
            # дублирующую запись уже получили раньше. log.exception() (не
            # log.error()) - чтобы в файле был виден полный traceback.
            log.exception("IMAGE PROCESS ERROR (распознавание по картинке)")

        return card
import os

from engines.knowledge_engine import KnowledgeEngine
from resolver.dropdown_resolver import DropdownResolver
from classifier.history_classifier import HistoryClassifier
from classifier.card_classifier import CardClassifier
from classifier.learning_classifier import LearningClassifier
from classifier.trace_classifier import TraceClassifier

from engines.engine import ResolverEngine
from resolver.excel_name_builder import ExcelNameBuilder
from resolver.special_product_resolver import SpecialProductResolver

from services.image_description_service import ImageDescriptionService
from processors.card_image_processor import CardImageProcessor


def _create_image_engine():
    # Выбор движка ИИ-распознавания по картинке через переменную
    # окружения IMAGE_ENGINE - позволяет сравнить варианты (Anthropic
    # / Yandex AI Studio) на одних и тех же карточках, не трогая код.
    # По умолчанию (переменная не задана) - Anthropic, как и раньше.
    # Импорт конкретного класса - ЛЕНИВЫЙ (внутри if/else), а не на
    # уровне модуля: если для выбранного варианта не задан свой ключ
    # или не установлена своя зависимость, падает только он, а не
    # оба сразу при обычном импорте decision_engine.py.
    engine_choice = os.getenv("IMAGE_ENGINE", "anthropic").strip().lower()

    if engine_choice == "yandex":
        from engines.yandex_image_description_engine import (
            YandexImageDescriptionEngine,
        )
        return YandexImageDescriptionEngine()

    from engines.image_description_engine import ImageDescriptionEngine
    return ImageDescriptionEngine()


class DecisionEngine:

    def __init__(self, learning_history):
        self.learning_history = learning_history
        self.knowledge = KnowledgeEngine()
        self.dropdown = DropdownResolver(self.knowledge.product_repository)
        self.history_classifier = HistoryClassifier(self.knowledge, learning_history)
        self.card_classifier = CardClassifier(self.knowledge)
        self.learning_classifier = LearningClassifier(self.knowledge)
        self.trace_classifier = TraceClassifier()
        self.product_engine = ResolverEngine(self.knowledge)
        self.special_products = SpecialProductResolver()
        self._decide_count = 0
        self._flush_every = 20

        # Распознавание по картинке - ТОЛЬКО для карточек, которые
        # обычная классификация не смогла определить (см. decide()
        # ниже). Инициализация может упасть (нет ключа нужного
        # сервиса, библиотека не установлена и т.п.) - это не должно
        # ронять весь движок, просто отключает эту подстраховку.
        # Какой именно сервис используется - см. _create_image_engine()
        # выше (переменная окружения IMAGE_ENGINE).
        try:
            image_engine = _create_image_engine()
            image_service = ImageDescriptionService(image_engine)
            self.image_processor = CardImageProcessor(image_service)
        except Exception as e:
            print(f"IMAGE PROCESSOR INIT ERROR (распознавание по картинке отключено): {e}")
            self.image_processor = None

    def decide(self, card, remember=True):

        # ==========================================================
        # 1. SPECIAL PRODUCT
        # ==========================================================
        special = self.special_products.resolve(card)

        if special:
            result = self.product_engine.classify(card)

            result.product = special["product"]
            result.dropdown = special["dropdown"]
            result.display_name = special["display_name"]
            result.code = special["code"]
            result.source = special["source"]
            result.confidence = special["confidence"]
            result.review = special["review"]
            result.quantity = getattr(card, "quantity", "")
            result.material = getattr(card, "material", "")
            result.trace.add(
                "SPECIAL_PRODUCT",
                f"Специальное правило: {special['source']}"
            )
            print(
                "[DECISION] SPECIAL:",
                card.url,
                "->",
                result.product,
                result.code,
            )
            return result
        # ==========================================================
        # 2. ОСНОВНАЯ КЛАССИФИКАЦИЯ
        # ==========================================================
        result = self.product_engine.classify(card)
        result.quantity = getattr(card, "quantity", "")
        if not result.material:
            result.material = getattr(card, "material", "")
        # ==========================================================
        # 3. DROPDOWN
        #
        # Пропускаем ТОЛЬКО если material_codes конкретного товара уже
        # дал код по материалу (result.material_code_resolved - see
        # resolver/result_builder.py). Раньше здесь стояло
        # `result.material and result.code`, но result.material
        # выставляется MaterialResolver'ом даже когда material_codes у
        # товара пуст (общий fallback find_known_material_group, см.
        # resolver/material_resolver.py) - а result.code при этом мог
        # быть просто плоским "code" из products.py. В паре с любым
        # словом-материалом из общего словаря это ложно считалось
        # "материал уже определён" и полностью пропускало выбор
        # dropdown-варианта, даже когда товар различается по полу/
        # назначению/механизму/объёму, а не по материалу вообще.
        # ==========================================================
        material_already_resolved = bool(result.material_code_resolved)

        if material_already_resolved:
            result.trace.add(
                "DROPDOWN",
                "Пропущен: материал уже определён через material_codes "
                f"(код={result.code})"
            )
        elif self.dropdown.resolve(result.product):
            self.dropdown.resolve_code(result, card)
            print(
                "DROPDOWN RESOLVED:",
                result.product,
                "-> код:",
                result.code,
                "источник:",
                result.source,
            )
            result.trace.add(
                "DROPDOWN",
                f"Вариант по материалу/спекам: "
                f"код={result.code}, "
                f"источник={result.source}, "
                f"уверенность={result.confidence}"
            )
        # ==========================================================
        # 4. CARD CACHE
        # ==========================================================
        result_from_card = self.card_classifier.apply(card, result)

        if result_from_card:
            builder = ExcelNameBuilder()
            result_from_card.dropdown = builder.build(
                card,
                result_from_card.product,
            )
            result_from_card.display_name = result_from_card.dropdown

            print(
                "[DECISION] CARD_CACHE:",
                card.url,
                "->",
                result_from_card.product,
                result_from_card.code,
            )
            return result_from_card
        # ==========================================================
        # 5. TRACE
        # ==========================================================
        result = self.trace_classifier.apply(card, result)
        # ==========================================================
        # 6. HISTORY
        # ==========================================================
        result = self.history_classifier.apply(result, card)
        # ==========================================================
        # 7. LEARNING
        # ==========================================================
        result = self.learning_classifier.apply(result)
        # ==========================================================
        # 7.5. ИИ-РАСПОЗНАВАНИЕ ПО КАРТИНКЕ (последний резерв)
        #
        # Только если код так и не определился ВСЕМИ обычными
        # путями (текст, breadcrumb, trace/history/learning) - это
        # платный внешний запрос, поэтому не тратим его на карточки,
        # которые и так удалось классифицировать. card.image_description
        # запрашивается один раз и добавляет отдельное поле IMAGE_DESC
        # в скоринг (см. resolver/candidate_scorer.py) - с весом,
        # сравнимым с CLEANED, т.к. это целевой, надёжный сигнал.
        # ==========================================================
        if not result.code and self.image_processor:

            self.image_processor.process(card)

            if getattr(card, "image_description", ""):

                print(
                    "[IMAGE FALLBACK]",
                    card.url,
                    "->",
                    card.image_description,
                )

                retried = self.product_engine.classify(card)
                retried.quantity = getattr(card, "quantity", "")
                if not retried.material:
                    retried.material = getattr(card, "material", "")

                if self.dropdown.resolve(retried.product):
                    self.dropdown.resolve_code(retried, card)

                if retried.code:
                    retried.trace.add(
                        "IMAGE_FALLBACK",
                        f"Определено по описанию с картинки: "
                        f"{card.image_description}"
                    )
                    result = retried
        # ==========================================================
        # 8. EXCEL NAME
        # ==========================================================
        builder = ExcelNameBuilder()
        result.dropdown = builder.build(card, result.product)
        result.display_name = result.dropdown
        # ==========================================================
        # 9. SAVE CARD
        # ==========================================================
        if remember:
            self.remember(card, result)
        # ==========================================================
        # 10. FINAL
        # ==========================================================
        result.trace.add(
            "FINAL",
            f"Итог: код={result.code or '-'}, "
            f"источник={result.source or '-'}, "
            f"уверенность={result.confidence}, "
            f"проверка={result.review}"
        )
        return result

    # ==========================================================
    # REMEMBER (вынесено из decide() шага 9 отдельным методом)
    #
    # Нужен отдельно от decide(), потому что классификация теперь
    # может выполняться в ОТДЕЛЬНОМ процессе (см.
    # processors/ozon_auto_processor.py::CLASSIFIER_WORKERS -
    # ProcessPoolExecutor с собственным DecisionEngine на каждый
    # процесс, decide(card, remember=False) там). card_repository
    # каждого worker-процесса - это ЕГО СОБСТВЕННАЯ копия в памяти
    # процесса, и "запоминание" туда бесполезно (никогда не попадёт
    # обратно в главный процесс и не будет сохранено в
    # storage/runtime_cards.json). Поэтому "запоминание" перенесено
    # в ГЛАВНЫЙ процесс - он получает готовые (card, result) обратно
    # от воркера и вызывает remember() на СВОЁМ, единственном,
    # реально сохраняемом на диск DecisionEngine.
    # ==========================================================
    def remember(self, card, result):

        if result.review:
            return

        self.knowledge.card_repository.remember(card, result)
        self._decide_count += 1
        print(
            "[CARD SAVE]",
            card.url,
            "code=",
            result.code,
            "product=",
            result.product,
        )
        print(
            "[CARD COUNT]",
            self._decide_count,
            "/",
            self._flush_every,
        )
        if self._decide_count % self._flush_every == 0:
            print(
                "[CARD FLUSH]",
                "count=",
                self._decide_count,
            )
            self.knowledge.card_repository.flush()
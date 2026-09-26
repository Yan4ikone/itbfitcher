from cleaner.product_cleaner import clean_text
from cleaner.product_extractor import ProductExtractor
from utils.quantity_extractor import extract_quantity
from utils.tokenizer import lemmatized_tokens


class ProductParser:

    def __init__(self):
        self.extractor = ProductExtractor()

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def parse(self, card):

        texts = []

        if card.title:
            texts.append(card.title)
        if card.slug:
            texts.append(card.slug)
        if card.description:
            texts.append(card.description)
        if card.material:
            texts.append(card.material)
        if card.quantity:
            texts.append(card.quantity)
        if getattr(card, "image_description", ""):
            # Без этого CandidateFinder вообще не находил бы товары
            # по описанию с картинки (он ищет кандидатов по токенам
            # raw_text) - даже с высоким весом в скоринге ниже, самих
            # кандидатов просто не было бы в списке для оценки.
            texts.append(card.image_description)
        # ДОБАВЛЕНО (2026-09-26, products-dict-gradation-audit.md,
        # обновление 15): запоминаем текст, который реально НАЗЫВАЕТ
        # товар (title/slug/description/material/quantity/
        # image_description), ДО подмешивания specs/sections/features
        # ниже - см. подробное объяснение прямо под "cleaned_text_only"
        # дальше по функции.
        text_only = " ".join(texts)

        for key, value in card.specs.items():
            if not value:
                continue

            texts.append(str(value))

        for section in card.sections.values():
            if isinstance(section, dict):
                for value in section.values():
                    if value:
                        texts.append(str(value))
            elif isinstance(section, list):
                for value in section:
                    if value:
                        texts.append(str(value))
            elif section:
                texts.append(str(section))
        for value in card.features.values():
            if value:
                texts.append(str(value))

        raw_text = " ".join(texts)
        cleaned, _, _ = clean_text(raw_text)
        # Отдельно чистим ТОЛЬКО текст описания продавца (card.description) -
        # раньше здесь ошибочно стояло то же самое `cleaned`, что и в
        # cleaned_text ниже (полная склейка title+slug+description+specs+
        # sections+features). Из-за этого в candidate_scorer.py поля
        # DESCRIPTION(200)/DESC_ALIAS(300) были БУКВАЛЬНО тем же текстом,
        # что и CLEANED(350)/CLEANED_ALIAS(250) - одно и то же совпадение
        # засчитывалось дважды под разными именами, и оба поля были
        # одинаково загрязнены ЛЮБЫМ значением характеристики (specs), а
        # не только тем, что продавец реально написал в текстовом описании
        # товара. Разбор: карточка "Ручка и кронштейн для открывания
        # защелки капота" ушла в код "наклейка" ИСКЛЮЧИТЕЛЬНО из-за
        # характеристики Тип="Наклейка автомобильная" (продавец ошибся с
        # полем) - в описании товара слова "наклейка" вообще нет, но оно
        # всё равно засчиталось и как SPECS, и как CLEANED, и (по этой
        # самой причине) как "DESCRIPTION" - из-за чего решение ошибочно
        # считалось "подтверждённым текстом продавца про этот товар"
        # (has_direct_text_support=True, resolver/result_builder.py) и НЕ
        # уходило на ИИ-подтверждение по картинке, хотя должно было (по
        # прямому указанию Яна - см. engines/decision_engine.py, шаг 7.5).
        # products-dict-gradation-audit.md.
        description_cleaned, _, _ = clean_text(card.description or "")
        # ДОБАВЛЕНО (2026-09-26, обновление 15) - тот же класс проблемы,
        # что и у description выше, только для CLEANED - САМОГО тяжёлого
        # по весу поля во всём скоринге (350 у CandidateScorer, больше,
        # чем TITLE=250 и DESCRIPTION=200 вместе с запасом). Пока эта
        # переменная (`cleaned`, полная склейка ВСЕХ полей, включая
        # specs/sections/features) шла в ключ "cleaned_text" - ОДНО
        # случайное совпадение постороннего значения характеристики
        # засчитывалось СРАЗУ в трёх весовых корзинах одновременно:
        # CLEANED(350, через этот ключ) + SPECS(до 450) + SPEC_TYPE(300,
        # если ключ характеристики - "Тип"/"Тип товара") - до 1100+ очков
        # от ОДНОГО стороннего спек-значения, тогда как настоящий сигнал
        # (буквальное совпадение в TITLE у истинного товара) весит всего
        # 250. Разбор: карточка "(A J W K) Пропорциональный
        # Электромагнитный Клапан..." (заголовок и описание чётко
        # называют клапан) получила код держателя ИСКЛЮЧИТЕЛЬНО из-за
        # постороннего значения характеристики "держатель" - тройной
        # счёт по CLEANED+SPECS+SPEC_TYPE (1058 очков) перевесил честное
        # совпадение "клапан" в TITLE+DESCRIPTION+CLEANED от настоящего
        # текста (800 очков). specs/sections/features и так уже честно
        # учитываются через отдельные, однократные веса SPECS/SPEC_TYPE
        # ниже - незачем ЕЩЁ РАЗ давать им максимальный вес поля CLEANED.
        cleaned_text_only, _, _ = clean_text(text_only)
        product = self.extractor.extract(cleaned)
        quantity = extract_quantity(raw_text)

        if quantity:
            product = f"{product} {quantity}"

        spec_values = []

        for value in card.specs.values():
            if value:
                spec_values.append(str(value).lower())
        for k, v in card.specs.items():
            print(f"   {k}: {v}")
        return {
            "title": card.title.lower(),
            "slug": card.slug.lower(),
            "description": description_cleaned.lower(),
            "cleaned_text": cleaned_text_only.lower(),
            "search_text": raw_text.lower(),
            "specs": spec_values,
            "material": getattr(card, "material", ""),
            "quantity": getattr(card, "quantity", ""),
            "specs_dict": {
                k: str(v).lower()
                for k, v in card.specs.items()
            },
            "breadcrumbs": [
                str(item).lower()
                for item in getattr(card, "breadcrumbs", [])
            ],
            "tokens": lemmatized_tokens(raw_text),
            "product_name": product,
            "image_description": str(
                getattr(card, "image_description", "") or ""
            ).lower(),
        }
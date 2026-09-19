from modules.classification_result import ClassificationResult

# ----------------------------------------------------------------------
# Типы совпадений (см. resolver/candidate_scorer.py::candidate.add) в
# полях, которые продавец заполнил ИМЕННО про этот конкретный товар -
# заголовок/URL/текстовое описание товара/описание с картинки (и их
# алиас-варианты, включая "_SIMILAR"). В отличие от них, BREADCRUMB/
# SPEC_TYPE/SPECS - это категория/характеристики Ozon (структурные
# метаданные, которые продавец мог заполнить в общем шаблоне неверно -
# см. кейс "ручка переключения передач", ошибочно classified как
# "ручной инструмент" по чужой категории продавца), а PATTERN/
# SCORE_WORD ищут по всему объединённому тексту сразу и не позволяют
# отличить попадание в заголовок от попадания в общую характеристику -
# поэтому оба сознательно НЕ считаются "прямым" подтверждением.
#
# CLEANED сюда сознательно НЕ входит (убран после разбора кейса "Ручка
# и кронштейн..."): это очищенный текст ВСЕЙ склейки (title+slug+
# description+specs+sections+features - см. parser/product_parser.py),
# а не только текста про сам товар - совпадение в нём может быть точно
# такой же generic-характеристикой, как и в SPECS/SPEC_TYPE (тот самый
# кейс: Тип="Наклейка автомобильная" совпал и как SPECS, и как CLEANED,
# хотя ни в заголовке, ни в реальном описании товара слова "наклейка"
# нет). DESCRIPTION/DESC_ALIAS теперь считаются ТОЛЬКО по очищенному
# card.description (текст, который продавец реально написал о товаре) -
# раньше он ошибочно совпадал с CLEANED буквально один в один (см.
# parser/product_parser.py), из-за чего одно и то же generic-совпадение
# засчитывалось дважды и вдобавок ошибочно считалось "прямым текстом
# продавца про этот товар".
# ----------------------------------------------------------------------
_DIRECT_TEXT_PREFIXES = (
    "TITLE",
    "SLUG",
    "DESCRIPTION",
    "DESC_ALIAS",
    "IMAGE_DESC",
)


def _has_direct_text_support(matches):

    for match in matches:

        match_type = match.get("type", "")

        if any(match_type.startswith(prefix) for prefix in _DIRECT_TEXT_PREFIXES):
            return True

    return False


class ResultBuilder:

    def build(self, winner, candidates):

        result = ClassificationResult()

        if winner is None:
            result.source = "NOT_FOUND"
            return result

        result.product = winner.product
        result.product_scores = candidates
        result.code = winner.code
        result.default_code = winner.code
        result.source = "PRODUCTS"
        result.confidence = min(winner.score, 100)
        result.has_direct_text_support = _has_direct_text_support(winner.matches)

        # Флаг ручной проверки и причина (NO_CANDIDATES / LOW_CONFIDENCE /
        # AMBIGUOUS / RESOLVED_VIA_EXTRA_DESCRIPTION) должны дойти до
        result.review = winner.review
        result.comment = winner.reason

        if winner.review and candidates:
            result.alternatives = {
                c.code: c.product
                for c in candidates[1:4]
                if c.code
            }
        # ------------------------------------------------------
        # Мульти-товарный листинг (см. product_resolver.py::
        # _clear_ambiguous_multi_product_code) - winner.code уже
        # очищен там, если среди кандидатов с максимальным score
        # было несколько РАЗНЫХ кодов. alternatives строим по ВСЕМ
        # настоящим тай-кандидатам сразу (а не только по первым трём
        # после победителя, как в общем случае выше) - победителя как
        # такового здесь нет, и куратор выбирает вручную (см.
        # комментарий к ячейке кода, ozon_auto_processor.py::
        # apply_result).
        #
        # result.product НЕ переписываем на склейку через " / "
        # ("переключатель кнопочный / переключатель поворотный") - по
        # прямому указанию Яна такие двойные наименования ставить не
        # нужно (products-dict-gradation-audit.md, обновление (11), п.6).
        # Остаётся одно название (winner.product, уже выставлено выше) -
        # весь список реальных вариантов куратор видит в комментарии к
        # ячейке кода через alternatives, без задваивания в самом
        # наименовании.
        # ------------------------------------------------------
        if (
            winner.reason == "AMBIGUOUS"
            and not winner.code
            and winner.tied_alternatives
        ):
            # winner.tied_alternatives ({название: код}) снят в
            # product_resolver.py ДО обнуления winner.code - сам
            # winner это тот же объект, что и первый элемент
            # candidates, поэтому пересчитывать коды из candidates
            # здесь уже нельзя (код победителя там тоже пуст).
            result.alternatives = {
                code: name
                for name, code in winner.tied_alternatives.items()
            }
            # winner.score всё ещё содержит "сырой" счёт (score
            # кандидата НЕ обнуляется в _clear_ambiguous_multi_product_
            # code, только code/material_code) - если оставить строку
            # 24 (result.confidence = min(winner.score, 100)) как
            # единственный источник, куратор в Excel/логе увидит
            # "Уверенность: 100%" одновременно с ПУСТЫМ кодом, что
            # выглядит как противоречие (зафиксировано на реальном
            # прогоне Test_machine_2: "выключатель поворотный /
            # выключатель кнопочный" и "решетка радиатора / решетка" -
            # оба показали CONFIDENCE 100 при пустом коде). Здесь явно
            # обнуляем, как и для DROPDOWN_UNRESOLVED.
            result.confidence = 0

        if winner.material:

            result.material = winner.material

        if winner.material_code:

            result.code = winner.material_code
            # Только этот путь означает, что код реально подобран по
            # material_codes конкретного товара - см.
            # engines/decision_engine.py::material_already_resolved.
            result.material_code_resolved = True
        result.trace.add(
            "PRODUCT",
            f"{winner.product} ({winner.score})"
        )

        for match in winner.matches:

            result.trace.add(
                match["type"],
                f'+{match["points"]} {match["text"]}',
            )

        return result
import time
import traceback


def process_classifier_task(item, decision_engine, card_builder):
    """
    Один элемент классификации.
    Используется внутри ProcessPoolExecutor.
    """
    start = time.perf_counter()
    result_data = {
        "success": False,
        "row_number": item["row_number"],
        "url": item["url"],
        "product": "",
        "display_name": "",
        "code": "",
        "source": "",
        "confidence": None,
        "review": False,
        "error": "",
    }
    try:

        card = card_builder(
            item["url"],
            item["parsed"],
            raw_text=item["parsed"].get(
                "description",
                ""
            ),
        )

        # Исходное наименование товара из Excel
        # последний шанс определить код, если по богатому заголовку с
        # маркетплейса ни один товар не подошёл (см.
        # resolver/product_resolver.py::_resolve_with_excel_title).
        excel_title = str(item.get("excel_title", "") or "").strip()

        if excel_title:
            card.excel_title = excel_title

        result = decision_engine.decide(card, remember=False)
        result_data["success"] = True
        result_data["product"] = (
            getattr(result, "product", "")
            or ""
        )
        result_data["display_name"] = (
            getattr(result, "display_name", "")
            or getattr(result, "dropdown", "")
            or ""
        )
        result_data["code"] = (
            getattr(result, "code", "")
            or ""
        )
        result_data["source"] = (
            getattr(result, "source", "")
            or ""
        )
        result_data["confidence"] = (getattr(result, "confidence", None))
        result_data["review"] = bool(getattr(result, "review", False))


    except Exception as exc:

        result_data["error"] = repr(exc)
        result_data["traceback"] = (traceback.format_exc())
    result_data["elapsed"] = (time.perf_counter() - start)

    return result_data
from dictionaries.all_dictionaries import MATERIAL_ALIASES
from modules.classification_result import ClassificationResult
from modules.product_scorer import score_products


def get_material_code(material_codes_dict, card):

    if not material_codes_dict:
        return "", ""

    parts = []

    if card.cleaned_text:
        parts.append(card.cleaned_text)

    if card.slug:
        parts.append(card.slug)

    if card.title:
        parts.append(card.title)

    for value in card.specs.values():

        if value:
            parts.append(str(value))

    text = " ".join(parts).lower()

    for key, value in MATERIAL_ALIASES.items():

        if isinstance(value, list):

            aliases = [
                key.lower(),
                *[
                    alias.lower()
                    for alias in value
                ]
            ]

            if any(alias in text for alias in aliases):

                material = key.lower()

                if material in material_codes_dict:

                    return (
                        material,
                        str(material_codes_dict[material])
                    )

        else:

            if key.lower() in text:

                material = value.lower()

                if material in material_codes_dict:

                    return (
                        material,
                        str(material_codes_dict[material])
                    )

    return "", ""

def classify_product(card, knowledge):

    result = ClassificationResult()
    result.original_name = card.title
    manual = knowledge.get_manual(card.url)

    if manual:
        result.product = manual["description"].lower().strip()
        result.dropdown = manual["description"]
        result.code = str(manual["code"])

        result.source = "MANUAL"
        result.confidence = 100

        return result
    candidates = score_products(card, knowledge)
    print("=" * 60)
    print("Название:", card.title)
    print("Количество кандидатов:", len(candidates))

    if candidates:
        print("Первый кандидат:", candidates[0])
    else:
        print("Кандидатов нет")
    result.product_scores = candidates

    for c in candidates[:10]:

        matches = []

        for m in c["matches"]:
            matches.append(
                f"+{m['points']} {m['type']} {m['text']}"
            )

        result.trace.add(
            "PRODUCT_SCORE",
            f"{c['product']} "
            f"score={c['score']}\n"
            + "\n".join(matches)
        )

    if not candidates:
        result.source = "NOT_FOUND"
        return result

    product = candidates[0]["product"]
    info = knowledge.get_product(product)
    result.product = product
    result.source = "PRODUCTS"
    result.confidence = 40
    code = knowledge.get_default_code(product)

    if code:
        result.default_code = str(code)
        result.code = str(code)

    material_codes = knowledge.get_material_codes(product)

    if material_codes:

        material, code = get_material_code(
            material_codes,
            card
        )

        if code:

            result.material = material
            result.code = code

        else:

            result.review = True
            result.alternatives = material_codes

    return result

from modules.product_cleaner import clean_text


def normalize_card(card):

    log = []
    text_parts = []

    if card.slug:
        text_parts.append(card.slug)

    if card.title:
        text_parts.append(card.title)

    if card.description:
        text_parts.append(card.description)

    for value in card.specs.values():

        if value:
            text_parts.append(str(value))

    text = " ".join(text_parts)

    log.append(f"Исходный текст:\n{text}")

    cleaned_text, removed, replaced = clean_text(text)
    # card.quantity = extract_quantity(cleaned_text)
    # card.material = extract_material(cleaned_text)
    # card.package = extract_package(cleaned_text)
    # card.brand = extract_brand(cleaned_text)
    # card.country = extract_country(cleaned_text)

    log.extend(replaced)

    if removed:

        log.append(
            "Удалено: " + ", ".join(sorted(removed))
        )

    card.cleaned_text = cleaned_text
    card.normalizer_log = log
    log.append("")
    log.append("Источники:")

    if card.slug:
        log.append(f"URL      : {card.slug}")

    if card.title:
        log.append(f"TITLE    : {card.title}")

    if card.description:
        log.append(f"DESC     : {card.description}")

    if card.material:
        log.append(f"MATERIAL : {card.material}")

    if card.quantity:
        log.append(f"QUANTITY : {card.quantity}")

    return card
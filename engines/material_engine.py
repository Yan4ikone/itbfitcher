from collections import Counter


def choose_by_material(similar_products, card):

    material = (
        card.specs.get("Материал")
        or ""
    ).strip().lower()

    if not material:
        return None

    filtered = []

    for item in similar_products:

        materials: Counter = item.materials

        if material in materials:
            filtered.append(item)

    if not filtered:
        return None

    counter = Counter()

    for item in filtered:

        counter[item.code] += item.count

    return counter.most_common(1)[0][0]
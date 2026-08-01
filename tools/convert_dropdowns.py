from pprint import pformat

from dictionaries.dropdown_lists import DROPDOWN_LISTS

GROUP_ALIASES = {

    "металл": "metal",
    "метал": "metal",
    "пласт": "plastic",
    "пластик": "plastic",
    "дерево": "wood",
    "дерев": "wood",
    "стекло": "glass",
    "стекл": "glass",
    "кожа": "leather",
    "текстиль": "textile",
    "текст": "textile",
    "неткан": "textile",
    "резина": "rubber",
    "керамика": "ceramic",
    "муж": "male",
    "жен": "female",
    "дет": "child",
    "электро": "electric",
    "ручной": "manual",
    "быт": "household"
}


def detect_group(name):

    if isinstance(name, list):
        name = " ".join(name)
    name = str(name).lower()

    for key, value in GROUP_ALIASES.items():

        if key in name:
            return value

    return "other"

new_dropdowns = {}

for product, variants in DROPDOWN_LISTS.items():

    new_dropdowns[product] = {
        "title": "Выберите вариант",
        "variants": []
    }

    if isinstance(variants, dict):

        for code, name in variants.items():

            if isinstance(name, list):
                names = []

                for item in name:
                    if isinstance(item, dict):
                        names.append(str(item.get("name", "")))
                    else:
                        names.append(str(item))
                display_name = ", ".join(names)

            else:
                display_name = str(name)
            new_dropdowns[product]["variants"].append({
                "code": str(code),
                "name": display_name,
                "group": detect_group(display_name)
            })
    elif isinstance(variants, list):

        for item in variants:

            if not isinstance(item, dict):
                continue

            code = item.get("code", "")
            name = item.get("name", "")
            display_name = str(name)
            new_dropdowns[product]["variants"].append({
                "code": str(code),
                "name": display_name,
                "group": detect_group(display_name)
            })
with open(
        "dropdown_lists_v2.py",
        "w",
        encoding="utf-8"
) as f:
    f.write("DROPDOWN_LISTS = ")
    f.write(
        pformat(
            new_dropdowns,
            width=140,
            sort_dicts=False
        )
    )
print("Готово.")
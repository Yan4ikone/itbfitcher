from pprint import pformat

from dropdown_lists import DROPDOWN_LISTS


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

    name = name.lower()

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

    for code, name in variants.items():

        new_dropdowns[product]["variants"].append({

            "code": code,

            "name": name,

            "group": detect_group(name)

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
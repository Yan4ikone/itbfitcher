from copy import deepcopy

from dictionaries.products import PRODUCTS
from MainApp import CATEGORY_RULES
from MainApp import NORMALIZE_DICT


def migrate_category_rules():

    products = deepcopy(PRODUCTS)

    for pattern, product_name in CATEGORY_RULES.items():

        if product_name not in products:
            continue

        products[product_name].setdefault(
            "patterns",
            []
        )

        if pattern not in products[product_name]["patterns"]:
            products[product_name]["patterns"].append(
                pattern
            )

    return products


def migrate_normalize_dict(products):

    for alias, product_name in NORMALIZE_DICT.items():

        if product_name not in products:
            continue

        products[product_name].setdefault(
            "aliases",
            []
        )

        if alias not in products[product_name]["aliases"]:
            products[product_name]["aliases"].append(
                alias
            )

    return products


def save_products(products):

    with open(
            "PRODUCTS_MERGED.py",
            "w",
            encoding="utf-8"
    ) as f:

        f.write("PRODUCTS = {\n\n")

        for product_name in sorted(products):

            info = products[product_name]

            code = info.get(
                "code",
                ""
            )

            patterns = sorted(
                list(
                    set(
                        info.get(
                            "patterns",
                            []
                        )
                    )
                )
            )

            aliases = sorted(
                list(
                    set(
                        info.get(
                            "aliases",
                            []
                        )
                    )
                )
            )

            if not patterns and not aliases:
                continue

            f.write(
                f'    "{product_name}": {{\n'
            )

            f.write(
                f'        "code": "{code}",\n'
            )

            f.write(
                '        "patterns": [\n'
            )

            for pattern in patterns:

                f.write(
                    f'            r"{pattern}",\n'
                )

            f.write(
                '        ],\n'
            )

            f.write(
                '        "aliases": [\n'
            )

            for alias in aliases:

                f.write(
                    f'            "{alias}",\n'
                )

            f.write(
                '        ]\n'
            )

            f.write(
                '    },\n\n'
            )

        f.write("}\n")


if __name__ == "__main__":

    products = migrate_category_rules()

    products = migrate_normalize_dict(
        products
    )

    save_products(products)

    print(
        "Создан файл PRODUCTS_MERGED.py"
    )
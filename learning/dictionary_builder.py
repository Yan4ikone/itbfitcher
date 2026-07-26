import os

import pandas as pd

from dictionaries.all_dictionaries import REMOVE_WORDS
from learning.importer import load_learning_history
from repositories.product_repository import ProductRepository
from classifier.normalizer import normalize_name


def normalize_for_dictionary(text: str) -> str:

    text = normalize_name(text)

    if not text:
        return ""

    words = text.lower().split()
    result = [
        word
        for word in words
        if not word.isdigit()
        and word not in REMOVE_WORDS
    ]

    return " ".join(result).strip()


def build_dictionaries(input_path: str):

    history = load_learning_history(input_path)
    repository = ProductRepository()
    df = pd.read_excel(input_path)
    desc_col = df.columns[1]
    code_col = df.columns[2]
    goods_stats = {}

    for _, row in df.iterrows():

        source_name = str(row[desc_col]).strip()
        normalized_name = normalize_for_dictionary(source_name)
        code = str(row[code_col]).strip()

        if (
            not code
            or code == "0"
            or code.lower() == "nan"
        ):
            continue

        if (
            not normalized_name
            or normalized_name == "nan"
        ):
            continue

        info = goods_stats.setdefault(
            normalized_name,
            {
                "codes": {},
                "examples": set(),
                "sources": []
            }
        )

        info["sources"].append({
            "source": source_name,
            "normalized": normalized_name,
            "code": code
        })

        info["codes"][code] = (
            info["codes"].get(code, 0) + 1
        )

        info["examples"].add(source_name)

    conflict_rows = []

    for product_name, info in history.items():

        codes = info["codes"]

        if len(codes) <= 1:
            continue

        for code, count in codes.items():

            conflict_rows.append({

                "Есть в PRODUCTS":
                    "ДА"
                    if repository.has(product_name)
                    else "НЕТ",

                "Наименование":
                    product_name,

                "Код":
                    code,

                "Количество":
                    count
            })

    conflicts_path = os.path.join(os.path.dirname(input_path), "CONFLICTS.xlsx")
    pd.DataFrame(conflict_rows).to_excel(conflicts_path, index=False)
    products_path = os.path.join(os.path.dirname(input_path), "PRODUCTS_CANDIDATES.py")

    with open(products_path, "w", encoding="utf-8") as f:

        f.write("PRODUCTS = {\n")

        for product_name, info in goods_stats.items():

            if repository.has(product_name):
                continue

            codes = info["codes"]

            if len(codes) != 1:
                continue

            code = next(iter(codes))
            aliases = []

            for example in sorted(info["examples"]):

                alias = normalize_name(example)

                if not alias:
                    continue

                alias = alias.lower().strip()

                if alias == product_name:
                    continue

                if alias not in aliases:
                    aliases.append(alias)

            patterns = []
            words = product_name.split()

            if len(words) >= 2:

                patterns.append(
                    ".*".join(
                        word[:5]
                        for word in words
                    )
                )

            f.write(f'    "{product_name}": {{\n')
            f.write(f'        "code": "{code}",\n')
            f.write(f'        "patterns": {patterns!r},\n')
            f.write(f'        "aliases": {aliases!r}\n')
            f.write("    },\n")

        f.write("}\n")

    return products_path, conflicts_path
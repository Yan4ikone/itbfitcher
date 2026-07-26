from collections import Counter
from pathlib import Path

import pandas as pd

from classifier.similarity_engine import extract_features, tokenize
from modules.product_card import ProductCard


LEARNING_HISTORY_DB = Path("learning/learning_history.json")

def import_verified_file(excel_path: str):

    history = load_learning_history(excel_path)
    save_learning_history(history)
    export_learning_history(history, Path(excel_path).with_name("LEARNING_HISTORY.xlsx"))

    return history


def load_learning_history(input_path: str) -> dict:

    history = {}

    try:
        df = pd.read_excel(input_path)

    except Exception:
        return history

    columns = {str(c).lower(): c for c in df.columns}
    desc_col = next((columns[c] for c in columns if "опис" in c), None)
    code_col = next((columns[c] for c in columns if "тнвэд" in c), None)
    material_col = next((columns[c] for c in columns if "материал" in c), None)

    if desc_col is None:
        return history

    for _, row in df.iterrows():

        description = str(row.get(desc_col, "")).strip()

        if not description:
            continue

        name = description.lower()
        card = ProductCard()
        card.title = description
        card.cleaned_text = description
        material = ""

        if material_col is not None:

            material = str(row.get(material_col, "")).strip()

            if material and material.lower() != "nan":
                card.specs["Материал"] = material
        code = ""

        if code_col is not None:

            code = str(row.get(code_col, "")).strip()

        if name not in history:

            history[name] = {
                "description": description,
                "tokens": tokenize(card.cleaned_text),
                "features": extract_features(card),
                "codes": Counter(),
                "materials": Counter()
            }

        if code and code != "0" and code.lower() != "nan":
            history[name]["codes"][code] += 1

        if material and material.lower() != "nan":
            history[name]["materials"][material.lower()] += 1

    return history


def save_learning_history(history):

    import json

    serializable = {}

    for name, item in history.items():

        serializable[name] = {
            "description": item["description"],
            "tokens": item["tokens"],
            "features": item["features"],
            "codes": dict(item["codes"]),
            "materials": dict(item["materials"])
        }

    with open(LEARNING_HISTORY_DB, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)


def export_learning_history(history, output):

    rows = []

    for name, info in history.items():

        for code, count in info["codes"].items():

            rows.append({
                "Описание": info["description"],
                "Код": code,
                "Количество": count,
                "Материалы": ", ".join(
                    f"{m}:{c}"
                    for m, c in info["materials"].items()
                )
            })
    pd.DataFrame(rows).to_excel(
        output,
        index=False
    )
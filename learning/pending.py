from pathlib import Path
from pprint import pformat

PENDING_PRODUCTS = Path("pending_products.py")

def load_pending_products():

    if not PENDING_PRODUCTS.exists():
        return {}

    namespace = {}

    with open(PENDING_PRODUCTS, "r", encoding="utf-8") as f:

        exec(f.read(), namespace)

    return namespace.get("PENDING_PRODUCTS", {})

def save_pending_products(data):

    with open(PENDING_PRODUCTS, "w", encoding="utf-8") as f:

        f.write("PENDING_PRODUCTS = ")
        f.write(pformat(data, width=140, sort_dicts=False))
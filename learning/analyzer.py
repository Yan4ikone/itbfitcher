from dictionaries.all_dictionaries import KNOWN_DROPDOWNS


class LearningAnalyzer:

    def __init__(self, runtime):
        self.runtime = runtime

    def analyze(self):

        report = {
            "new_products": [],
            "new_aliases": [],
            "new_material_codes": [],
            "new_dropdowns": [],
            "new_dropdown_variants": []
        }

        for product, info in self.runtime.pending.items():

            description = product
            code = str(info.get("code", ""))
            materials = info.get("materials", {})
            runtime_product = self.runtime.repository.get_product(description)

            if runtime_product is None:
                report["new_products"].append({
                    "description": description,
                    "code": code,
                    "count": info.get("count", 1)
                })
                continue

            known_materials = runtime_product.get("material_codes", {})

            for material in materials:

                if material not in known_materials:
                    report["new_material_codes"].append({
                        "product": description,
                        "material": material,
                        "code": code
                    })

            aliases = runtime_product.get("aliases", [])

            if (
                    description != runtime_product.get("display_name", "").lower()
                    and description not in aliases
            ):
                report["new_aliases"].append({
                    "product": description,
                    "alias": description
                })

            if description in KNOWN_DROPDOWNS:

                dropdown = self.runtime.get_dropdown(description)

                exists = False

                if dropdown:

                    for item in dropdown["variants"]:

                        if str(item["code"]) == code:
                            exists = True
                            break

                if not exists:
                    report["new_dropdown_variants"].append({
                        "product": description,
                        "code": code
                    })

        return report
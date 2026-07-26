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

        for card in self.runtime.all_cards():

            manual = self.runtime.manual.get(card["url"])

            if not manual:
                continue

            description = manual["description"].lower().strip()
            code = str(manual["code"]).strip()

            runtime_product = self.runtime.repository.get_product(description)

            if runtime_product is None:
                report["new_products"].append({
                    "description": description,
                    "code": code,
                    "count": 1
                })

                continue

            product_name = description
            product_info = runtime_product
            material = (
                    card.get("material", "")
                    or card.get("specs", {}).get("Материал", "")
            ).strip().lower()

            known_materials = product_info.get("material_codes", {})

            if (
                    material
                    and material not in known_materials
            ):
                report["new_material_codes"].append({
                    "product": product_name,
                    "material": material,
                    "code": code
                })

            aliases = product_info.get("aliases", [])
            original_title = card.get("title", "").strip().lower()

            if (
                    original_title
                    and original_title != description
                    and original_title not in aliases
            ):
                report["new_aliases"].append({
                    "product": product_name,
                    "alias": original_title
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
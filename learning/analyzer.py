from cleaner.alias_builder import AliasBuilder
from learning.name_normalizer import normalize_dictionary_name
from learning.product_matcher import ProductMatcher
from learning.review_models import LearningReport, NewProduct, NewAlias, NewMaterialCode, NewDropdownVariant


class LearningAnalyzer:

    def __init__(self, runtime):
        self.runtime = runtime
        self.matcher = ProductMatcher(runtime.product_repository)
        self.alias_builder = AliasBuilder()

    def analyze(self):
        print("ANALYZER START")
        report = LearningReport()

        for card in self.runtime.all_cards():
            manual = self.runtime.manual.get(
                card.get("normalized_url", card["url"])
            )

            print("CARD:", card["url"])
            print("NORMALIZED:", card.get("normalized_url"))
            print("MANUAL:", manual)

            if not manual:
                continue

            raw_description = manual["description"].strip()
            description = normalize_dictionary_name(raw_description).lower()
            code = str(manual["code"]).strip()
            runtime_product = self.runtime.get_product(description)
            print("DESCRIPTION:", description)
            print("PRODUCT EXISTS:", runtime_product)
            material = (
                    card.get("material", "")
                    or card.get("specs", {}).get("Материал", "")
            ).strip().lower()

            if not runtime_product:

                matched = self.matcher.match(description, code)
                print()
                print("MATCH")
                print("DESCRIPTION:", description)
                print("CODE:", code)
                print("RESULT:", matched)
                print()

                if matched:
                    report.new_aliases.append(
                        NewAlias(
                            product=matched["product"],
                            alias=description,
                        )
                    )
                    continue

                report.new_products.append(
                    NewProduct(
                        description=description,
                        code=code,
                        title=card.get("title", ""),
                        url=card.get("url", ""),
                        material=material,
                    )
                )
                continue

            product_name = description
            product_info = runtime_product

            if isinstance(runtime_product, dict) and "product" in runtime_product:
                product_name = runtime_product["product"]
                product_info = self.runtime.get_product(product_name)
            known_materials = product_info.get("material_codes", {})

            if (
                    material
                    and material not in known_materials
            ):
                report.new_material_codes.append(
                    NewMaterialCode(
                        product=product_name,
                        material=material,
                        code=code
                    )
                )

            candidate_aliases = self.alias_builder.build(
                card,
                description,
            )

            aliases = {
                normalize_dictionary_name(alias).lower()
                for alias in product_info.get("aliases", [])
            }

            aliases.add(
                normalize_dictionary_name(product_name).lower()
            )

            for alias in candidate_aliases:

                alias = normalize_dictionary_name(alias).lower()

                if (
                        not alias
                        or alias in aliases
                ):
                    continue

                report.new_aliases.append(
                    NewAlias(
                        product=product_name,
                        alias=alias,
                    )
                )

            dropdown = self.runtime.get_dropdown(description)
            if dropdown:

                dropdown = self.runtime.get_dropdown(description)
                exists = False

                if dropdown:

                    for item in dropdown["variants"]:

                        if str(item["code"]) == code:
                            exists = True
                            break

                if not exists:
                    report.new_dropdown_variants.append(
                        NewDropdownVariant(
                            product=description,
                            code=code
                        )
                    )
        return report
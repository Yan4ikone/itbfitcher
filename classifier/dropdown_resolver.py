from dictionaries.dropdown_lists import DROPDOWN_LISTS


class DropdownResolver:

    def resolve(self, product):

        if product not in DROPDOWN_LISTS:
            return ""

        return product

    def resolve_code(self, result, card):

        data = DROPDOWN_LISTS.get(result.product)

        if not data:
            return

        parts = [
            card.title,
            card.description,
            card.cleaned_text,
            result.material
        ]

        text = " ".join(
            str(x)
            for x in parts
            if x
        ).lower()

        for variant in data["variants"]:

            group = variant.get("group", "").lower()

            if group and group in text:

                result.code = variant["code"]
                result.dropdown_group = group
                result.source = "DROPDOWN"
                result.confidence = 90

                return

        variants = data.get("variants", [])

        if not variants:
            return

        first = variants[0]
        result.code = first["code"]
        result.dropdown_group = first.get("group", "")
        result.review = True
        result.source = "DROPDOWN_FIRST"
        result.confidence = 60

        result.alternatives = {
            item["code"]: item["name"]
            for item in data["variants"]
        }
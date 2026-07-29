from dictionaries.all_dictionaries import MATERIAL_ALIASES


class MaterialResolver:

    def __init__(self):
        pass

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def resolve(self, candidate, parsed):

        material_codes = candidate.info.get("material_codes", {})

        if not material_codes:
            return ""

        text = self._collect_text(parsed)
        material = self._find_material(text)

        if not material:
            return ""

        candidate.material = material
        code = material_codes.get(material)

        if code:
            candidate.material_code = str(code)
            return str(code)

        return ""

    # ==========================================================
    # TEXT
    # ==========================================================

    def _collect_text(self, parsed):

        parts = []

        for key in ("title", "slug", "description", "cleaned_text", "specs", "material"):

            value = parsed.get(key)

            if value:
                parts.append(value.lower())

        return " ".join(parts)

    # ==========================================================
    # MATERIAL SEARCH
    # ==========================================================

    def _find_material(self, text):

        if not text:
            return ""

        for material, aliases in MATERIAL_ALIASES.items():

            if isinstance(aliases, str):
                aliases = [aliases]

            variants = [
                material.lower(),
                *[
                    alias.lower()
                    for alias in aliases
                ]
            ]
            for variant in variants:
                if variant in text:
                    return material.lower()

        return ""
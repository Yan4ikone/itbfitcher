from dictionaries.all_dictionaries import MATERIAL_ALIASES


class MaterialResolver:

    def __init__(self):
        pass

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


    def _collect_text(self, parsed):

        parts = []

        for key in ("title", "slug", "description", "cleaned_text", "material"):

            value = parsed.get(key)

            if value:
                parts.append(str(value).lower())

        specs = parsed.get("specs", [])

        if isinstance(specs, list):
            parts.extend(specs)

        elif isinstance(specs, str):
            parts.append(specs.lower())

        return " ".join(parts)


    def _find_material(self, text):

        if not text:
            return ""

        priority = ["силикон", "смола", "пластик", "abs пластик", "искусственная кожа", "натуральная кожа",
            "текстиль", "металл", "стекло"]

        for wanted in priority:

            aliases = MATERIAL_ALIASES.get(wanted, [])

            if isinstance(aliases, str):
                aliases = [aliases]

            variants = [wanted] + aliases

            for variant in variants:
                if variant.lower() in text:
                    return wanted
        return ""
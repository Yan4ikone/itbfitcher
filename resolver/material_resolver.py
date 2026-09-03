from dictionaries.all_dictionaries import MATERIAL_ALIASES
from utils.material_extractor import (
    is_excluded_material_key,
    strip_excluded_material_mentions,
    find_known_material_group,
)


class MaterialResolver:

    def __init__(self):
        pass

    def resolve(self, candidate, parsed):

        material_codes = candidate.info.get("material_codes", {})
        text = self._collect_text(parsed)

        if material_codes:

            material = self._find_material(text, material_codes)

            if material:
                candidate.material = material
                code = material_codes.get(material)

                if code:
                    candidate.material_code = str(code)
                    return str(code)

            return ""

        # material_codes у товара пуст - НОВЫЕ правила "материал ->
        # код" теперь пишутся как dropdown-варианты, а не сюда (см.
        # learning/analyzer.py). Но candidate.material (сам ФАКТ, не
        # код) всё равно нужен - его использует MaterialAxisResolver
        # в DropdownResolver, чтобы найти подходящий dropdown-вариант.
        # Определяем факт по ОБЩЕМУ словарю MATERIAL_ALIASES, без
        # привязки к конкретному товару - тем же способом, каким
        # GenderAxisResolver определяет пол через GENDER_ALIASES.
        #
        # Код здесь намеренно НЕ назначаем (return "") - для товаров
        # с material_codes код возвращался отсюда напрямую и мог
        # полностью пропустить DropdownResolver (см.
        # engines/decision_engine.py: "material_already_resolved").
        # Для товаров без material_codes это не нужно - код должен
        # прийти именно из dropdown-варианта.
        candidate.material = find_known_material_group(text)

        return ""


    def _collect_text(self, parsed):

        parts = []

        for key in ("title", "slug", "description", "cleaned_text", "material"):

            value = parsed.get(key)

            if value:
                # Свободный текст (в Excel-пути характеристики и описание
                # могут быть склеены в одну строку) - вырезаем упоминания
                # стельки/подкладки/подошвы, чтобы их материал не подменял
                # материал верха/основной части при определении кода.
                parts.append(
                    strip_excluded_material_mentions(str(value)).lower()
                )

        specs = parsed.get("specs_dict")

        if isinstance(specs, dict):
            # specs_dict сохраняет ключи характеристик - в отличие от
            # "specs" (плоский список значений без ключей), что как раз
            # и не давало отличить "Материал верха" от "Материал стельки".
            for key, value in specs.items():
                if not value:
                    continue
                if is_excluded_material_key(key):
                    # Материал стельки/подкладки/подошвы и т.п. -
                    # намеренно не участвует в поиске материала товара.
                    continue
                parts.append(str(value).lower())
        else:
            # Обратная совместимость с местами, которые всё ещё передают
            # старый плоский список значений без ключей.
            legacy_specs = parsed.get("specs", [])

            if isinstance(legacy_specs, list):
                parts.extend(legacy_specs)
            elif isinstance(legacy_specs, str):
                parts.append(legacy_specs.lower())

        return " ".join(parts)

    def _find_material(self, text, material_codes):

        if not text:
            return ""

        for wanted in material_codes.keys():

            aliases = MATERIAL_ALIASES.get(wanted, [])

            if isinstance(aliases, str):
                aliases = [aliases]

            variants = [wanted] + aliases

            for variant in variants:
                if variant.lower() in text:
                    return wanted
        return ""
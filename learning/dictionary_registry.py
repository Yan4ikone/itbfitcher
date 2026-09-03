"""
Реестр общих словарей (материал/пол/...), которые куратор может
расширять прямо из окна обучения через вкладку "Словарь".

Чтобы добавить новый редактируемый словарь (например, когда для
"назначения" накопятся реальные данные - см. PURPOSE_ALIASES) -
достаточно добавить одну запись в DICTIONARY_REGISTRY. Ничего в
learning_window.py/builder.py/analyzer.py трогать не нужно, они все
читают этот реестр.
"""

from dictionaries import all_dictionaries


DICTIONARY_REGISTRY = {

    "material": {
        "label": "Материалы",
        "constant": "MATERIAL_ALIASES",
    },

    "gender": {
        "label": "Пол / возрастная группа",
        "constant": "GENDER_ALIASES",
    },

    # "purpose": {
    #     "label": "Назначение",
    #     "constant": "PURPOSE_ALIASES",
    # },  # пока пустой словарь без реальных данных - см. сессию про
    #     # GENDER_ALIASES, включим когда появятся реальные слова.
}


def dictionary_choices():
    """[(ключ, подпись), ...] для комбобокса выбора словаря в UI."""
    return [
        (key, meta["label"])
        for key, meta in DICTIONARY_REGISTRY.items()
    ]


def get_dictionary(key):
    """Живой словарь (canonical -> [aliases]) по ключу реестра.
    Всегда читает АКТУАЛЬНОЕ состояние модуля (importlib.reload
    делает builder/save_dictionaries перед записью) - поэтому не
    кэшируем результат."""

    meta = DICTIONARY_REGISTRY.get(key)

    if not meta:
        return {}

    return getattr(all_dictionaries, meta["constant"], {}) or {}


def group_choices(key):
    """Существующие канонические группы словаря (для комбобокса) -
    напр. для "material": ['металл', 'пластик', 'дерево', ...]."""

    return sorted(get_dictionary(key).keys())

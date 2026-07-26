import pandas as pd
import re


def build_replace_dict(original_path, corrected_path):
    """Строит словарь замен на основе двух файлов."""
    df_orig = pd.read_excel(original_path, sheet_name='Sheet1')
    df_corr = pd.read_excel(corrected_path, sheet_name='Sheet1')

    replace_dict = {}

    for _, row in df_orig.iterrows():
        orig_name = str(row['Описание']).strip().lower()

        # Находим соответствующую строку во втором файле по 'пн'
        corr_row = df_corr[df_corr['пн'] == row['пн']]
        if not corr_row.empty:
            corr_name = str(corr_row.iloc[0]['Описание']).strip().lower()

            if orig_name != corr_name:
                # Простая замена: если одно слово заменено на другое
                # или короткая фраза на другую короткую фразу
                if len(orig_name.split()) == 1 and len(corr_name.split()) == 1:
                    replace_dict[orig_name] = corr_name
                # Или если одна фраза является частью другой
                elif orig_name in corr_name or corr_name in orig_name:
                    replace_dict[orig_name] = corr_name
    return replace_dict


# --- Пример использования ---
# replace_dict = build_replace_dict('input.xlsx', 'corrected.xlsx')
# print(replace_dict)
# {'ночной светильник': 'ночник', 'bluetooth колонка': 'колонка', ...}

def apply_replace_dict(text, replace_dict):
    """Применяет словарь замен к тексту."""
    text_lower = text.lower()
    for old, new in replace_dict.items():
        # Используем границы слов, чтобы не заменять части других слов
        if re.search(rf"\b{re.escape(old)}\b", text_lower):
            return new
    return text  # Если замен не найдено
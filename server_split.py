"""
Разделение входного файла по серверам/машинам и сборка результатов
обратно в один файл.

Принцип разделения: копируем исходный файл ЦЕЛИКОМ N раз (сохраняя
100% форматирования, стилей, формул шаблона), и в каждой копии
очищаем колонки ссылки (D/E) для строк, НЕ доставшихся этой машине.
processors/ozon_auto_processor.py сам пропускает строки без ссылки
(get_url_from_row возвращает None) - значит каждая копия обработает
только свою часть, и обрабатывать нужно ИМЕННО эту копию, а не
писать отдельный урезанный файл с нуля (что потеряло бы всё
форматирование источника).

Принцип сборки: все N файлов-результатов - это копии ОДНОЙ и той же
структуры (тот же файл, что раздали), просто с разными строками
заполненными. Берём любой из них как основу и для каждой строки
переносим колонки результата (B/C/K/L/M/N) из того файла, который
эту строку реально обработал.
"""

import os
import shutil

import openpyxl
from copy import copy


# Колонки, которые processors/ozon_auto_processor.py заполняет по
# результату обработки - именно их нужно перенести при сборке.
RESULT_COLUMNS = ["B", "C", "K", "L", "M", "N"]


def _get_url(ws, row):
    """Та же логика, что get_url_from_row в ozon_auto_processor.py -
    ссылка может быть гиперссылкой в D/E или обычным текстом,
    начинающимся с http."""

    for col in ("D", "E"):

        cell = ws[f"{col}{row}"]

        if cell.hyperlink:
            return cell.hyperlink.target

        value = cell.value

        if isinstance(value, str) and value.startswith("http"):
            return value

    return None


def find_rows_with_url(ws, max_row=None):
    """Список номеров строк (начиная со 2, шапка - первая строка),
    у которых есть ссылка - именно эти строки процессор реально
    обрабатывает, только их и делим между машинами."""

    if max_row is None:
        max_row = ws.max_row

    rows = []

    for row in range(2, max_row + 1):

        if _get_url(ws, row):
            rows.append(row)

    return rows


def distribute_evenly(rows, n):
    """Делит список номеров строк на n примерно равных частей
    (остаток распределяется по первым частям, как в Delitel.py)."""

    n = max(1, int(n))

    per_machine = len(rows) // n
    extra = len(rows) % n

    chunks = []
    start = 0

    for i in range(n):

        size = per_machine + (1 if i < extra else 0)

        chunks.append(rows[start:start + size])

        start += size

    return chunks


def split_by_servers(source_path, n, output_dir, counts=None, log=None):
    """Разбивает source_path на n файлов-копий для n машин/серверов.

    counts: необязательный список из n чисел - сколько строк отдать
    каждой машине (для ручной настройки количества, как просил Yan -
    "с изменением количества"). Если не задан - делится поровну.

    Возвращает список путей к созданным файлам.
    """

    def _log(msg):
        if log:
            log(msg)

    os.makedirs(output_dir, exist_ok=True)

    workbook = openpyxl.load_workbook(source_path)
    sheet = workbook.active

    rows = find_rows_with_url(sheet)

    _log(f"Всего строк со ссылкой: {len(rows)}")

    if counts:

        if sum(counts) != len(rows):
            raise ValueError(
                f"Сумма количеств ({sum(counts)}) не совпадает с "
                f"числом строк ({len(rows)})"
            )

        chunks = []
        start = 0

        for count in counts:
            chunks.append(rows[start:start + count])
            start += count

    else:
        chunks = distribute_evenly(rows, n)

    base_name = os.path.splitext(os.path.basename(source_path))[0]

    output_paths = []

    for i, chunk in enumerate(chunks, start=1):

        dest_path = os.path.join(
            output_dir,
            f"{base_name}_machine_{i}.xlsx",
        )

        shutil.copy(source_path, dest_path)

        _log(f"Машина {i}: {len(chunk)} строк -> {dest_path}")

        dest_wb = openpyxl.load_workbook(dest_path)
        dest_ws = dest_wb.active

        assigned = set(chunk)

        for row in rows:

            if row in assigned:
                continue

            # Не отданная этой машине строка - очищаем ссылку, чтобы
            # processor её пропустил (get_url_from_row вернёт None).
            dest_ws[f"D{row}"] = None
            dest_ws[f"E{row}"] = None

        dest_wb.save(dest_path)
        output_paths.append(dest_path)

    return output_paths


def merge_server_results(result_paths, output_path, log=None):
    """Собирает результаты с N машин обратно в один файл.

    Все result_paths - копии одной и той же структуры (результат
    split_by_servers), просто с разными строками, заполненными
    каждой машиной. Берём первый файл как основу и переносим в него
    колонки результата из того файла, который реально обработал
    каждую конкретную строку (определяем по заполненному коду C).
    """

    def _log(msg):
        if log:
            log(msg)

    if not result_paths:
        raise ValueError("Нет файлов для сборки")

    base_path = result_paths[0]
    base_wb = openpyxl.load_workbook(base_path)
    base_ws = base_wb.active

    max_row = base_ws.max_row

    other_sheets = []

    for path in result_paths[1:]:
        wb = openpyxl.load_workbook(path)
        other_sheets.append(wb.active)
        max_row = max(max_row, wb.active.max_row)

    all_sheets = [base_ws] + other_sheets

    merged_rows = 0

    # Колонки ссылки переносим ВСЕГДА (даже для строк базового
    # файла) - в базовом файле ссылки для чужих строк были очищены
    # при разделении (см. split_by_servers), их нужно восстановить
    # из файла, который эту строку реально обработал.
    LINK_COLUMNS = ["D", "E"]

    for row in range(2, max_row + 1):

        # Находим, какой из файлов реально обработал эту строку -
        # тот, где в колонке C (код) есть значение.
        source_ws = None

        for ws in all_sheets:

            code = ws[f"C{row}"].value if row <= ws.max_row else None

            if code not in (None, "", 0):
                source_ws = ws
                break

        if source_ws is None:
            continue

        for col in LINK_COLUMNS:

            cell = source_ws[f"{col}{row}"]

            if cell.hyperlink:
                base_ws[f"{col}{row}"] = cell.value
                base_ws[f"{col}{row}"].hyperlink = cell.hyperlink.target
            else:
                base_ws[f"{col}{row}"] = cell.value

        if source_ws is base_ws:
            merged_rows += 1
            continue

        for col in RESULT_COLUMNS:
            base_ws[f"{col}{row}"] = source_ws[f"{col}{row}"].value

        merged_rows += 1

    base_wb.save(output_path)

    _log(f"Собрано строк с результатом: {merged_rows}")
    _log(f"Итоговый файл сохранён: {output_path}")

    return output_path

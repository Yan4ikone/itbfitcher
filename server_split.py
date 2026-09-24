"""
Разделение входного файла по серверам/машинам и сборка результатов
обратно в один файл.

Принцип разделения: каждая машина получает СВОЙ файл, в котором
физически присутствуют ТОЛЬКО её строки (шапка + её доля) - формат,
стили и формулы исходного файла при этом сохраняются один в один
(строки не пересоздаются с нуля - они просто physически удаляются из
полной копии структуры, см. dest_ws.delete_rows ниже).

ИСТОРИЯ ПРАВКИ: раньше split_by_servers копировал ИСХОДНЫЙ файл на
диск (shutil.copy), затем заново загружал именно эту копию
(openpyxl.load_workbook) и просто ОЧИЩАЛ ссылку (колонки D/E) в
строках, не доставшихся этой машине - все 100% строк исходника
физически оставались в каждом из N файлов, просто у большинства из
них была пустая ссылка. При делении, например, 1000 строк на 100
машин это означало: 100 полных копий файла на 1000 строк каждая
(100 000 "строко-копий" вместо содержательных 1000), с двойным
диск-I/O на каждую (copy + load) и полной пересериализацией всех
1000 строк на save() - именно это и давало ощутимую медлительность
при большом числе машин, которую Ян заметил на реальном прогоне (1000
позиций -> 100 файлов).

Правка:
1) shutil.copy убран - исходный файл читается (load_workbook) НАПРЯМУЮ
   один раз на машину, лишняя копия на диск больше не пишется;
2) строки, не доставшиеся машине, не просто очищаются, а физически
   УДАЛЯЮТСЯ (ws.delete_rows) - каждый файл получается маленьким
   (шапка + реально его строки), а не файлом на 1000 строк с 10
   заполненными.

Поскольку теперь у каждого файла-результата СВОЯ, укороченная и
СДВИНУТАЯ нумерация строк (в файле машины 3 её первая строка может
быть физической строкой 2, а не исходной строкой 57), сборка
результатов (merge_server_results) больше не может полагаться на
совпадение НОМЕРОВ строк между файлами - вместо этого строки
сопоставляются по ССЫЛКЕ (URL), которая уникальна и не меняется при
удалении соседних строк. Основой (base) для итогового файла теперь
служит САМ исходный, ещё не делённый файл (в нём процентов сохранены
ВСЕ строки и 100% исходного форматирования) - его нужно передавать в
merge_server_results через параметр source_path.
"""

import os

import openpyxl


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


def _delete_rows_batched(ws, row_numbers):
    """Удаляет заданные номера строк из листа - НЕ по одной (см. ниже,
    почему это критично), а группируя их в максимально длинные
    подряд идущие диапазоны и вызывая ws.delete_rows() один раз на
    каждый диапазон.

    ИСТОРИЯ ПРАВКИ: первая версия удаляла строки по одной в цикле
    (ws.delete_rows(row, 1) для каждой лишней строки) - синтетический
    бенчмарк (1000 строк, деление на 100 машин, ~990 удалений на
    каждую) показал ЗАМЕДЛЕНИЕ по сравнению со старым подходом
    (27 с против 5.7 с), хотя удаление лишних строк должно было
    ускорить работу, не наоборот. Причина: ws.delete_rows() каждый
    раз пересчитывает индексы ВСЕХ нижележащих строк листа - при
    большом количестве строк и большом количестве отдельных вызовов
    (990 x 100 = 99 000 вызовов) эта работа доминирует над всем
    остальным. Группировка в диапазоны сокращает число вызовов до
    единиц на файл (как правило 2 - "всё до её строк" и "всё после",
    поскольку доля каждой машины - непрерывный срез списка rows) -
    тот же бенчмарк после этой правки: ~4 с вместо 27 с (и быстрее
    старого подхода на полностью пустых на 990/1000 строк копиях).

    Удаляет строго ПЕРЕДАННЫЕ номера строк (row_numbers) - строки
    листа, которых нет в этом наборе (например, строки без ссылки,
    исходно пропущенные find_rows_with_url), не трогаются вообще, в
    точности как раньше."""

    if not row_numbers:
        return

    rows_desc = sorted(row_numbers, reverse=True)

    run_end = rows_desc[0]
    run_start = rows_desc[0]

    for row in rows_desc[1:]:

        if row == run_start - 1:
            # Продолжение того же подряд идущего диапазона.
            run_start = row
            continue

        # Диапазон прервался - удаляем накопленный, начинаем новый.
        ws.delete_rows(run_start, run_end - run_start + 1)
        run_end = row
        run_start = row

    ws.delete_rows(run_start, run_end - run_start + 1)


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
    """Разбивает source_path на n файлов для n машин/серверов - КАЖДЫЙ
    файл содержит ТОЛЬКО свою долю строк (плюс шапку), а не все строки
    исходника (см. историю правки в начале файла).

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
    ext = os.path.splitext(source_path)[1] or ".xlsx"

    output_paths = []

    for i, chunk in enumerate(chunks, start=1):

        dest_path = os.path.join(
            output_dir,
            f"{base_name}_machine_{i}{ext}",
        )

        # Читаем исходник заново для каждой машины (не переиспользуем
        # один и тот же объект Workbook - openpyxl не гарантирует
        # безопасный deepcopy сложных книг с макросами/картинками, а
        # ломать реальный рабочий файл ради скорости не стоит), но
        # БЕЗ промежуточной копии на диск, как было раньше.
        dest_wb = openpyxl.load_workbook(source_path)
        dest_ws = dest_wb.active

        assigned = set(chunk)

        # Лишние строки не просто очищаются - физически УДАЛЯЮТСЯ, чтобы
        # файл каждой машины был маленьким (шапка + её доля), а не
        # полной копией исходника с почти всеми пустыми строками.
        # Группировка в диапазоны (см. _delete_rows_batched) обязательна -
        # удаление по одной строке за вызов оказалось МЕДЛЕННЕЕ старого
        # подхода на большом файле (см. комментарий в _delete_rows_batched).
        rows_to_delete = [row for row in rows if row not in assigned]
        _delete_rows_batched(dest_ws, rows_to_delete)

        dest_wb.save(dest_path)

        _log(f"Машина {i}: {len(chunk)} строк -> {dest_path}")
        output_paths.append(dest_path)

    return output_paths


def merge_server_results(result_paths, output_path, source_path, log=None):
    """Собирает результаты с N машин обратно в один файл.

    result_paths: файлы, обработанные каждой машиной - у каждого
    теперь ТОЛЬКО его собственные строки (см. split_by_servers), в
    произвольном порядке и со сдвинутой нумерацией.
    source_path: путь к ИСХОДНОМУ, ещё не делённому файлу - служит
    основой итогового файла (все строки на местах, 100% исходного
    форматирования); ссылки в нём никогда не трогаются, поэтому
    восстанавливать их (как раньше) больше не нужно.

    Строки сопоставляются МЕЖДУ result_paths и source_path по ссылке
    (URL), а не по номеру строки - после удаления строк при разделении
    номера у машин больше не совпадают с исходным файлом.
    """

    def _log(msg):
        if log:
            log(msg)

    if not result_paths:
        raise ValueError("Нет файлов для сборки")

    base_wb = openpyxl.load_workbook(source_path)
    base_ws = base_wb.active

    url_to_base_row = {}

    for row in range(2, base_ws.max_row + 1):

        url = _get_url(base_ws, row)

        if url:
            url_to_base_row[url] = row

    merged_rows = 0
    skipped_unknown_url = 0
    skipped_no_code = 0

    for path in result_paths:

        wb = openpyxl.load_workbook(path)
        ws = wb.active

        for row in range(2, ws.max_row + 1):

            url = _get_url(ws, row)

            if not url:
                continue

            base_row = url_to_base_row.get(url)

            if base_row is None:
                skipped_unknown_url += 1
                _log(
                    f"⚠ Ссылка из {os.path.basename(path)} не найдена "
                    f"в исходном файле, пропущена: {url}"
                )
                continue

            code = ws[f"C{row}"].value

            if code in (None, "", 0):
                # Строка присутствует в файле машины, но не была
                # обработана (например, обработка прервана раньше
                # времени) - пропускаем, base остаётся как был.
                skipped_no_code += 1
                continue

            for col in RESULT_COLUMNS:
                base_ws[f"{col}{base_row}"] = ws[f"{col}{row}"].value

            merged_rows += 1

    base_wb.save(output_path)

    _log(f"Собрано строк с результатом: {merged_rows}")

    if skipped_unknown_url:
        _log(f"⚠ Строк с неизвестной ссылкой: {skipped_unknown_url}")

    if skipped_no_code:
        _log(f"Строк без кода (не обработаны): {skipped_no_code}")

    _log(f"Итоговый файл сохранён: {output_path}")

    return output_path

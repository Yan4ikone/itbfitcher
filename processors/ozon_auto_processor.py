import threading
import traceback
import time
import asyncio
import openpyxl

from learning.importer import load_learning_history
from parser.cdp_product_parser import CDPProductParser, BLOCKED_RESOURCE_TYPES, log
from engines.decision_engine import DecisionEngine
from modules.decision_logger import DecisionLogger

from pathlib import Path

from repositories.card_repository import CardRepository


class OzonAutoProcessor:

    # ==========================================================
    # НАСТРОЙКА МНОГОПОТОЧНОСТИ
    # ==========================================================

    MAX_WORKERS = 4

    def __init__(
            self,
            excel_path,
            logger=None,
            stats_callback=None,
            limit=None,
            skip_filled=False
    ):
        self.skip_filled = skip_filled
        self.excel_path = excel_path
        self.logger = logger
        self.limit = limit
        self.stats_callback = stats_callback

        self.stop_requested = False
        self.pause_requested = False

        self.pause_event = threading.Event()
        self.pause_event.set()

        self.total_rows = 0
        self.processed_rows = 0
        self.found_count = 0
        self.not_found_count = 0
        self.cached_count = 0

        self.learning_buffer = []

        p = Path(excel_path)

        self.result_path = str(
            p.with_name(
                f"{p.stem}_RESULT{p.suffix}"
            )
        )

        self.decision_logger = DecisionLogger()
        self.card_repository = CardRepository()
        # ------------------------------------------------------
        # Защита общей статистики
        # ------------------------------------------------------
        self.stats_lock = threading.Lock()
        # ------------------------------------------------------
        # DecisionEngine нельзя одновременно заставлять
        # писать CardRepository из нескольких потоков.
        # Поэтому decide() будет защищён этим lock.
        # ------------------------------------------------------
        self.engine_lock = threading.Lock()
    # ==========================================================
    # LOG
    # ==========================================================
    def log(self, text):

        print(text)

        if self.logger:
            self.logger(text)
    # ==========================================================
    # CACHE
    # ==========================================================
    def get_cached_card(self, url):

        if not url:
            return None

        card = self.card_repository.find_by_url(url)

        if card:
            return card

        return self.card_repository.find_by_normalized_url(url)
    # ==========================================================
    # PAUSE / RESUME / STOP
    # ==========================================================
    def pause(self):

        self.pause_requested = True
        self.pause_event.clear()
        self.log("Обработка приостановлена")

    def resume(self):

        self.pause_requested = False
        self.pause_event.set()
        self.log("Обработка продолжена")

    def stop(self):

        self.stop_requested = True

        # Разбудить ожидающие worker,
        # чтобы они могли увидеть stop_requested.
        self.pause_event.set()
        self.log("Получена команда остановки...")

    async def async_worker(
            self,
            worker_id,
            page,
            task_queue,
            result_queue,
            engine,
    ):
        """
        Один постоянный worker.
        У worker-а одна постоянная вкладка.
        Например:
            Worker 1 -> Page 1
            Worker 2 -> Page 2
            Worker 3 -> Page 3
            Worker 4 -> Page 4
        """

        parser = self.async_parser

        self.log(
            f"[OzonWorker-{worker_id}] "
            f"готов"
        )

        while True:

            task = await task_queue.get()

            try:
                if task is None:
                    return

                row, url, excel_name = task
                # ==================================================
                # STOP
                # ==================================================
                if self.stop_requested:
                    await result_queue.put({
                        "row": row,
                        "url": url,
                        "stopped": True,
                    })
                    continue
                # ==================================================
                # PAUSE
                # ==================================================
                while self.pause_requested:
                    await asyncio.sleep(
                        0.2
                    )
                if self.stop_requested:
                    await result_queue.put({
                        "row": row,
                        "url": url,
                        "stopped": True,
                    })
                    continue
                # ==================================================
                # CACHE
                # ==================================================
                cached_card = (self.get_cached_card(url))

                if cached_card:
                    await result_queue.put({
                        "row": row,
                        "url": url,
                        "cached": True,
                        "cached_card": cached_card,
                    })
                    continue
                # ==================================================
                # LOG
                # ==================================================
                self.log(
                    f"[OzonWorker-{worker_id}] "
                    f"Строка {row}: {url}"
                )
                # ==================================================
                # PARSE
                # ==================================================
                card = await parser.parse_url_async(page, url)
                # ==================================================
                # EXCEL TITLE
                # ==================================================
                if excel_name:
                    card.excel_title = (excel_name)
                # ==================================================
                # RESULT
                # ==================================================
                await result_queue.put({
                    "row": row,
                    "url": url,
                    "cached": False,
                    "card": card,
                })
            except Exception as exc:
                await result_queue.put({
                    "row": task[0],
                    "url": task[1],
                    "error": exc,
                    "traceback": traceback.format_exc(),
                })
            finally:

                task_queue.task_done()

    async def _run_async(
            self,
            rows_to_process,
            ws,
            wb,
            engine,
    ):
        """
        Главный async pipeline.
        Один Playwright connection.
        Один Browser Context.
        Четыре постоянные страницы.
        """
        self.async_parser = (CDPProductParser())
        # ======================================================
        # ONE CDP CONNECTION
        # ======================================================
        await self.async_parser.connect_async()

        context = (self.async_parser.async_context)

        self.log(
            "CDP подключён. "
            "Создаём постоянные вкладки..."
        )
        # ======================================================
        # 4 ПОСТОЯННЫЕ ВКЛАДКИ
        # ======================================================
        worker_count = min(
            self.MAX_WORKERS,
            len(rows_to_process),
        )
        pages = []

        for index in range(
                worker_count
        ):
            page = await context.new_page()

            # Блокируем только тяжёлые ресурсы.
            # Картинки блокируем как раньше —
            # URL изображений берутся из HTML/srcset.
            async def route_handler(
                    route
            ):
                try:
                    if (
                            route.request.resource_type
                            in BLOCKED_RESOURCE_TYPES
                    ):
                        await route.abort()
                    else:
                        await route.continue_()
                except Exception:
                    try:
                        await route.continue_()
                    except Exception:
                        pass
            await page.route(
                "**/*",
                route_handler,
            )
            pages.append(page)

            self.log(
                f"[OzonWorker-{index + 1}] "
                f"Page создана"
            )
        # ======================================================
        # QUEUES
        # ======================================================
        task_queue = asyncio.Queue()
        result_queue = asyncio.Queue()
        # ======================================================
        # ЗАДАЧИ
        # ======================================================
        for task in rows_to_process:
            if self.stop_requested:
                break
            await task_queue.put(
                task
            )
        # ======================================================
        # WORKERS
        # ======================================================
        workers = []

        for index, page in enumerate(
                pages
        ):
            workers.append(
                asyncio.create_task(
                    self.async_worker(
                        index + 1,
                        page,
                        task_queue,
                        result_queue,
                        engine,
                    )
                )
            )
        # ======================================================
        # STOP SIGNAL
        # ======================================================
        for _ in workers:
            await task_queue.put(
                None
            )
        # ======================================================
        # RESULTS
        # ======================================================
        completed = 0

        try:
            while (
                    completed
                    < len(rows_to_process)
            ):
                result_data = (
                    await result_queue.get()
                )
                completed += 1

                try:
                    # ==============================================
                    # ERROR
                    # ==============================================
                    if "error" in result_data:
                        self.log(
                            result_data.get(
                                "traceback",
                                "Неизвестная ошибка",
                            )
                        )
                        self.processed_rows += 1
                        self.print_progress()

                        continue
                    # ==============================================
                    # STOP
                    # ==============================================
                    if result_data.get("stopped"):
                        self.processed_rows += 1
                        self.print_progress()

                        continue

                    row = result_data["row"]
                    # ==============================================
                    # CACHE
                    # ==============================================
                    if result_data.get("cached"):

                        self.apply_cached_result(
                            ws,
                            row,
                            result_data[
                                "cached_card"
                            ],
                        )
                        self.cached_count += 1
                    # ==============================================
                    # NORMAL CARD
                    # ==============================================
                    else:

                        card = result_data["card"]
                        # ------------------------------------------
                        # DecisionEngine теперь выполняется здесь
                        # ------------------------------------------
                        with self.engine_lock:

                            result = engine.decide(card)
                        self.apply_result(
                            ws,
                            row,
                            card,
                            result,
                        )
                    # ==============================================
                    # PROGRESS
                    # ==============================================
                    self.processed_rows += 1
                    self.print_progress()
                    # ==============================================
                    # SAVE
                    # ==============================================
                    if (
                            self.processed_rows
                            % 20
                            == 0
                    ):
                        wb.save(
                            self.result_path
                        )

                        self.log(
                            "Файл сохранён"
                        )
                finally:

                    result_queue.task_done()

        finally:
            # ==================================================
            # WAIT WORKERS
            # ==================================================
            await asyncio.gather(
                *workers,
                return_exceptions=True,
            )
            # ==================================================
            # CLOSE 4 PAGES
            # ==================================================
            for page in pages:
                try:
                    await page.close()
                except Exception:

                    log.debug(
                        "Ошибка закрытия страницы",
                        exc_info=True,
                    )
            # ==================================================
            # CLOSE PLAYWRIGHT
            # ==================================================
            await self.async_parser.disconnect_async(close_browser=False)
    # ==========================================================
    # URL
    # ==========================================================

    def get_url_from_row(self, ws, row):

        for col in ("D", "E"):

            cell = ws[f"{col}{row}"]

            if cell.hyperlink:
                return cell.hyperlink.target

            value = cell.value

            if (
                    isinstance(value, str)
                    and value.startswith("http")
            ):
                return value
        return None
    # ==========================================================
    # APPLY CACHE RESULT
    # ==========================================================

    def apply_cached_result(
            self,
            ws,
            row,
            cached_card,
    ):
        description = (
            cached_card.get("display_name")
            or cached_card.get("product")
            or cached_card.get("description")
            or ""
        )
        code = str(
            cached_card.get(
                "code",
                "",
            )
        ).strip()

        if description:
            ws[f"B{row}"] = description

        if code and code not in (
                "0",
                "nan",
        ):
            try:
                ws[f"C{row}"] = int(code)
            except ValueError:
                ws[f"C{row}"] = code

            self.found_count += 1
            self.log(f"CACHE Описание: {description}")
            self.log(f"CACHE Код: {code}")

        else:

            self.not_found_count += 1

    # ==========================================================
    # APPLY NORMAL RESULT
    # ==========================================================

    def apply_result(
            self,
            ws,
            row,
            card,
            result,
    ):
        # ------------------------------------------------------
        # Excel title
        # ------------------------------------------------------

        # ВАЖНО:
        # card.excel_title должен быть установлен ДО decide().
        #
        # Это будет сделано в run(), перед отправкой worker.
        # Если decide() уже был вызван без него, значение B
        # не влияет на уже полученный результат.
        #
        # Поэтому ниже ничего не меняем.
        # ------------------------------------------------------
        ws[f"K{row}"] = (
            "Да"
            if result.new_product
            else ""
        )
        ws[f"L{row}"] = (
            "Да"
            if result.new_dropdown
            else ""
        )
        # ------------------------------------------------------
        # Decision Logger
        # ------------------------------------------------------
        self.decision_logger.save(card, result)
        # ------------------------------------------------------
        # Learning buffer
        # ------------------------------------------------------
        self.learning_buffer.append(
            {
                "url": card.url,
                "title": card.title,
                "description": card.description,
                "product": result.product,
                "code": result.code,
                "material": result.material,
            }
        )
        # ------------------------------------------------------
        # B
        # ------------------------------------------------------
        original = ws[f"B{row}"].value

        if result.dropdown:

            ws[f"B{row}"] = (result.dropdown)

        elif result.product:

            ws[f"B{row}"] = (result.product)

        else:

            ws[f"B{row}"] = original
        # ------------------------------------------------------
        # C
        # ------------------------------------------------------
        if result.code:
            try:
                ws[f"C{row}"] = int(
                    result.code
                )
            except ValueError:
                ws[f"C{row}"] = (
                    result.code
                )
        # ------------------------------------------------------
        # Statistics
        # ------------------------------------------------------

        if result.code:

            self.found_count += 1

            self.log(
                f"Описание: {result.dropdown}"
            )

            self.log(
                f"Товар: {result.product}"
            )

            self.log(
                f"Материал: {result.material}"
            )

            self.log(
                f"Код: {result.code}"
            )

            self.log(
                f"Источник: {result.source}"
            )

            self.log(
                f"Уверенность: "
                f"{result.confidence}%"
            )

            if result.review:
                self.log(
                    "⚠ Требуется проверка"
                )

        else:

            self.not_found_count += 1

            self.log(
                f"Описание: "
                f"{result.product}"
            )

            self.log(
                "Код не найден"
            )

    # ==========================================================
    # RUN
    # ==========================================================

    def run(self):

        self.start_time = time.time()

        self.log(
            "Открытие Excel..."
        )

        wb = openpyxl.load_workbook(
            self.excel_path
        )

        ws = wb.active

        rows_to_process = []

        # ==========================================================
        # СОБИРАЕМ СТРОКИ
        # ==========================================================

        for row in range(
                2,
                ws.max_row + 1
        ):

            url = self.get_url_from_row(
                ws,
                row,
            )

            current_code = (
                ws[f"C{row}"].value
            )

            if self.skip_filled:

                if current_code not in (
                        None,
                        "",
                        0,
                ):
                    continue

            if url:
                excel_name = str(
                    ws[f"B{row}"].value
                    or ""
                ).strip()

                rows_to_process.append(
                    (
                        row,
                        url,
                        excel_name,
                    )
                )
        # ==========================================================
        # LIMIT
        # ==========================================================
        if self.limit:
            rows_to_process = (
                rows_to_process[
                :self.limit
                ]
            )
        self.total_rows = len(
            rows_to_process
        )
        self.log(
            f"Всего строк: "
            f"{self.total_rows}"
        )
        if not rows_to_process:
            wb.save(
                self.result_path
            )
            self.print_summary()

            return
        # ==========================================================
        # LEARNING HISTORY
        # ==========================================================

        learning_history = (load_learning_history(self.excel_path))
        engine = DecisionEngine(learning_history
                                )
        try:

            asyncio.run(
                self._run_async(
                    rows_to_process,
                    ws,
                    wb,
                    engine,
                )
            )
        finally:

            wb.save(self.result_path)
        self.print_summary()
        # ==========================================================
        # ЗАПУСК CDP
        # ==========================================================
        #
        # Этот parser нужен только для гарантированного запуска
        # браузера/CDP.
        #
        # Он НЕ занимается товарами.
        # ==========================================================

        bootstrap_parser = (CDPProductParser())
        bootstrap_parser.connect()

        self.log(
            "CDP браузер готов."
        )

        # ==========================================================
        # ОЧЕРЕДЬ ЗАДАЧ
        # ==========================================================

        task_queue = queue.Queue()

        # ==========================================================
        # СОЗДАЁМ 4 ПОСТОЯННЫХ WORKER-А
        # ==========================================================

        worker_count = min(
            self.MAX_WORKERS,
            len(rows_to_process),
        )

        self.log(
            f"Запускаем "
            f"{worker_count} worker-а"
        )

        self.worker_threads = []

        for index in range(
                worker_count
        ):
            thread = threading.Thread(
                target=self.worker_loop,
                args=(
                    task_queue,
                    engine,
                ),
                name=f"OzonWorker-{index + 1}",
                daemon=True,
            )

            thread.start()

            self.worker_threads.append(
                thread
            )

        # ==========================================================
        # ЗАПОЛНЯЕМ ОЧЕРЕДЬ
        # ==========================================================

        for task in rows_to_process:

            if self.stop_requested:
                break

            task_queue.put(task)

        # ==========================================================
        # СТОП-СИГНАЛЫ ДЛЯ WORKER-ОВ
        # ==========================================================
        #
        # Каждый worker получает None и завершает свой цикл.
        # ==========================================================

        for _ in range(worker_count):
            task_queue.put(None)

        # ==========================================================
        # ГЛАВНЫЙ ЦИКЛ
        # ==========================================================
        #
        # Worker-ы парсят.
        #
        # Главный поток получает готовые результаты
        # и единственный изменяет Excel.
        # ==========================================================

        completed = 0

        try:

            while completed < len(
                    rows_to_process
            ):

                try:

                    result_data = (
                        self.worker_result_queue.get(
                            timeout=0.5
                        )
                    )

                except queue.Empty:

                    # Проверяем, не завершились ли worker-ы
                    # неожиданно.

                    if all(
                            not thread.is_alive()
                            for thread in self.worker_threads
                    ):
                        break

                    continue

                try:

                    completed += 1

                    # ==================================================
                    # ОШИБКА WORKER
                    # ==================================================

                    if "error" in result_data:
                        self.log(
                            result_data.get(
                                "traceback",
                                "Неизвестная ошибка",
                            )
                        )

                        self.processed_rows += 1

                        self.print_progress()

                        continue

                    # ==================================================
                    # STOP
                    # ==================================================

                    if result_data.get(
                            "stopped"
                    ):
                        self.processed_rows += 1

                        self.print_progress()

                        continue

                    row = result_data[
                        "row"
                    ]

                    # ==================================================
                    # CACHE
                    # ==================================================

                    if result_data.get(
                            "cached"
                    ):

                        cached_card = (
                            result_data[
                                "cached_card"
                            ]
                        )

                        self.apply_cached_result(
                            ws,
                            row,
                            cached_card,
                        )

                        self.cached_count += 1

                    # ==================================================
                    # NORMAL RESULT
                    # ==================================================

                    else:

                        card = (
                            result_data[
                                "card"
                            ]
                        )

                        result = (
                            result_data[
                                "result"
                            ]
                        )

                        self.apply_result(
                            ws,
                            row,
                            card,
                            result,
                        )

                    # ==================================================
                    # PROGRESS
                    # ==================================================

                    self.processed_rows += 1

                    self.print_progress()

                    # ==================================================
                    # SAVE EVERY 20
                    # ==================================================

                    if (
                            self.processed_rows
                            % 20
                            == 0
                    ):
                        wb.save(
                            self.result_path
                        )

                        self.log(
                            "Файл сохранён"
                        )

                finally:

                    self.worker_result_queue.task_done()

        except Exception:

            self.log(
                traceback.format_exc()
            )

        finally:

            # ======================================================
            # ЖДЁМ ЗАВЕРШЕНИЯ ВСЕХ WORKER-ОВ
            # ======================================================

            for thread in self.worker_threads:
                thread.join()

            # ======================================================
            # ФИНАЛЬНОЕ СОХРАНЕНИЕ EXCEL
            # ======================================================

            wb.save(
                self.result_path
            )

            # ======================================================
            # ТОЛЬКО ЗДЕСЬ закрываем bootstrap parser.
            #
            # close_browser=True закрывает общий браузер.
            # ======================================================

            try:

                bootstrap_parser.disconnect(
                    close_browser=True
                )

            except Exception:

                self.log(
                    traceback.format_exc()
                )

        self.print_summary()

    def worker_loop(self, task_queue, engine):
        """
        Постоянный worker-поток.

        Один поток:
            1. создаёт свой CDPProductParser
            2. подключается к браузеру
            3. обрабатывает несколько URL
            4. отключает parser
            5. завершается

        В результате Playwright никогда не передаётся
        между потоками.
        """

        parser = None

        try:
            # ------------------------------------------------------
            # Каждый worker получает СОБСТВЕННЫЙ parser
            # ------------------------------------------------------

            parser = CDPProductParser()
            parser.connect()

            self.log(
                f"[{threading.current_thread().name}] "
                f"CDP parser подключён"
            )

            # ------------------------------------------------------
            # Обрабатываем задачи
            # ------------------------------------------------------

            while True:

                task = task_queue.get()

                try:

                    # Специальная команда завершения
                    if task is None:
                        return

                    row, url, excel_name = task

                    # ----------------------------------------------
                    # STOP
                    # ----------------------------------------------

                    if self.stop_requested:
                        self.worker_result_queue.put({
                            "row": row,
                            "url": url,
                            "stopped": True,
                        })

                        continue

                    # ----------------------------------------------
                    # PAUSE
                    # ----------------------------------------------

                    self.pause_event.wait()

                    if self.stop_requested:
                        self.worker_result_queue.put({
                            "row": row,
                            "url": url,
                            "stopped": True,
                        })

                        continue

                    # ----------------------------------------------
                    # CACHE
                    # ----------------------------------------------

                    cached_card = self.get_cached_card(url)

                    if cached_card:
                        self.worker_result_queue.put({
                            "row": row,
                            "url": url,
                            "cached": True,
                            "cached_card": cached_card,
                        })

                        continue

                    # ----------------------------------------------
                    # LOG
                    # ----------------------------------------------

                    self.log(
                        f"[{threading.current_thread().name}] "
                        f"Строка {row}: {url}"
                    )

                    # ----------------------------------------------
                    # Ozon
                    # ----------------------------------------------

                    card = parser.parse_url(url)

                    # ----------------------------------------------
                    # Excel title
                    # ----------------------------------------------

                    if excel_name:
                        card.excel_title = excel_name

                    # ----------------------------------------------
                    # Pause
                    # ----------------------------------------------

                    self.pause_event.wait()

                    if self.stop_requested:
                        self.worker_result_queue.put({
                            "row": row,
                            "url": url,
                            "card": card,
                            "stopped": True,
                        })

                        continue

                    # ----------------------------------------------
                    # DecisionEngine
                    #
                    # Он изменяет общий CardRepository.
                    # Поэтому только один worker за раз.
                    # ----------------------------------------------

                    with self.engine_lock:

                        result = engine.decide(card)

                    # ----------------------------------------------
                    # Передаём результат главному потоку
                    # ----------------------------------------------

                    self.worker_result_queue.put({
                        "row": row,
                        "url": url,
                        "cached": False,
                        "card": card,
                        "result": result,
                    })

                except Exception as e:

                    self.worker_result_queue.put({
                        "row": row,
                        "url": url,
                        "error": e,
                        "traceback": traceback.format_exc(),
                    })

                finally:

                    task_queue.task_done()

        finally:

            # ------------------------------------------------------
            # КРИТИЧЕСКИ ВАЖНО:
            #
            # parser отключается внутри ТОГО ЖЕ потока,
            # в котором был создан.
            # ------------------------------------------------------

            if parser is not None:

                try:

                    parser.disconnect(
                        close_browser=False
                    )

                    self.log(
                        f"[{threading.current_thread().name}] "
                        f"CDP parser отключён"
                    )

                except Exception:

                    self.log(
                        traceback.format_exc()
                    )

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def print_progress(self):

        remaining = (
            self.total_rows
            - self.processed_rows
        )

        self.log(
            (
                f"Обработано: "
                f"{self.processed_rows}/"
                f"{self.total_rows} | "
                f"Осталось: "
                f"{remaining}"
            )
        )

        if self.stats_callback:

            self.stats_callback(
                self.total_rows,
                self.processed_rows,
                self.found_count,
                self.not_found_count,
            )

    # ==========================================================
    # SUMMARY
    # ==========================================================

    def print_summary(self):

        self.log("\n")
        self.log("=" * 60)

        self.log(
            "ОБРАБОТКА ЗАВЕРШЕНА"
        )

        self.log(
            f"Всего: {self.total_rows}"
        )

        self.log(
            f"Найдено: {self.found_count}"
        )

        self.log(
            f"Не найдено: "
            f"{self.not_found_count}"
        )

        self.log(
            f"Из кеша: "
            f"{self.cached_count}"
        )

        if self.total_rows:

            percent = round(
                (
                    self.found_count
                    / self.total_rows
                ) * 100,
                2,
            )

            self.log(
                f"Успешность: "
                f"{percent}%"
            )

        self.log("=" * 60)

        elapsed = round(
            time.time()
            - self.start_time
        )

        self.log(
            f"Время работы: "
            f"{elapsed} сек."
        )

        if self.processed_rows:

            avg = (
                elapsed
                / self.processed_rows
            )

            self.log(
                f"Среднее на товар: "
                f"{avg:.2f} сек."
            )

        if self.stats_callback:

            self.stats_callback(
                self.total_rows,
                self.total_rows,
                self.found_count,
                self.not_found_count,
            )
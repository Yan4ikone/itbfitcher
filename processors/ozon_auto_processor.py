import os
import threading
import traceback
import time
import random
import asyncio
import openpyxl
from concurrent.futures import ProcessPoolExecutor
from openpyxl.comments import Comment

from learning.importer import load_learning_history
from parser.cdp_product_parser import CDPProductParser, BLOCKED_RESOURCE_TYPES, log
from engines.decision_engine import DecisionEngine
from modules.decision_logger import DecisionLogger
from pathlib import Path
from repositories.card_repository import CardRepository
from excel.postprocessing import (
    apply_visual_postprocessing,
    apply_group_colors,
    REVIEW_FILL,
    REVIEW_FONT,
)


# ==================================================================
# CLASSIFIER PROCESS POOL - модуль-уровневые функции
#
# ОБЯЗАТЕЛЬНО модуль-уровневые (не методы класса) - ProcessPoolExecutor
# должен уметь ИМПОРТИРОВАТЬ их в дочернем процессе по имени (pickle
# хранит только "module.func", не сам код), связанный метод объекта
# OzonAutoProcessor для этого не годится.
#
# Архитектура (см. products-dict-gradation-audit.md, обновление (11),
# п.6) - две РАЗНЫЕ, независимые друг от друга группы воркеров:
#
# - MAX_WORKERS (браузерные вкладки, класс OzonAutoProcessor выше) -
#   ждут ответ от Ozon (сетевой I/O) + намеренная антибот-пауза.
#   Проверено Яном вручную - больше 2 вкладок не имеет смысла и
#   ухудшает результат (антибот реагирует на суммарную частоту
#   запросов с одного браузера).
# - CLASSIFIER_WORKERS (эта группа) - ЧИСТЫЙ CPU: очистка текста,
#   лемматизация (pymorphy3), скоринг кандидата против ~1500+ товаров
#   словаря. Никакого сетевого ожидания - только счёт. Именно эта
#   группа реально выигрывает от нескольких ядер процессора, и её
#   размер имеет смысл увеличивать независимо от MAX_WORKERS.
#
# Дизайн (создание DecisionEngine ОДИН РАЗ НА ПРОЦЕСС через
# initializer, а не на каждую карточку - иначе каждая карточка заново
# грузила бы весь словарь на 1500+ товаров) взят из уже
# протестированного Яном прототипа `processors/ozon_pipeline_test.py`
# (BROWSER_WORKERS=2, CLASSIFIER_WORKERS=4) - здесь он впервые подключён
# к реальному, боевому пайплайну вместо отдельного тестового скрипта.
# ==================================================================

_classifier_engine = None


def _init_classifier_worker(learning_history):
    """Выполняется РОВНО ОДИН РАЗ на каждый дочерний процесс пула -
    поднимает свой собственный DecisionEngine (свой словарь/индексы в
    памяти ЭТОГО процесса)."""

    global _classifier_engine

    _classifier_engine = DecisionEngine(learning_history)


def _classify_card(card):
    """Выполняется внутри дочернего процесса. remember=False -
    дочерний процесс НЕ пишет card_repository/runtime_cards.json (это
    его СОБСТВЕННАЯ копия в памяти процесса, обратно в главный процесс
    и на диск она не попадёт) - "запоминание" по результату делает
    ГЛАВНЫЙ процесс через DecisionEngine.remember(), получив (card,
    result) обратно (см. OzonAutoProcessor._classify_and_apply)."""

    global _classifier_engine

    result = _classifier_engine.decide(card, remember=False)

    return card, result


class OzonAutoProcessor:

    # ==========================================================
    # НАСТРОЙКА МНОГОПОТОЧНОСТИ
    # ==========================================================
    # ПРОВЕРЕНО НА ЖИВОМ ПРОГОНЕ (Test_machine_2, 2026-09-18) И
    # ОТКАЧЕНО ОБРАТНО: попытка поднять MAX_WORKERS до 4 (комментарий
    # ниже "4 ПОСТОЯННЫЕ ВКЛАДКИ" описывает более старый, судя по
    # всему никогда не проверенный на практике дизайн) дала РЕЗУЛЬТАТ
    # ХУЖЕ, а не лучше: 7.05 сек/товар вместо прежних ~6 сек/товар.
    # Причина - все "воркеры" это вкладки ОДНОГО и того же реального
    # браузера, подключённого через ОДИН CDP-коннекшн (см.
    # _run_async ниже - один CDPProductParser, один context). Пауза
    # WORKER_DELAY_MIN/MAX действительно ограничивает частоту запросов
    # ОТ ОДНОГО воркера, но НЕ ограничивает СУММАРНУЮ частоту запросов
    # к Ozon со всех вкладок сразу - при 4 воркерах общий поток
    # запросов к Ozon примерно вдвое чаще, чем при 2, а антибот-защита
    # Ozon (судя по всему) реагирует именно на суммарную частоту с
    # одного IP/браузера, а не на частоту отдельной вкладки. Поэтому
    # при 4 воркерах чаще срабатывает деградация/задержка ответа -
    # средняя скорость падает, а не растёт. Возвращено к 2 по прямому
    # указанию заказчика. Поднимать это число снова стоит только с
    # очень осторожным пошаговым тестом (например 2 -> 3, не 2 -> 4) и
    # с проверкой количества таймаутов/деградированных страниц в логе,
    # а не только средней скорости.
    MAX_WORKERS = 2
    # Пауза между запросами ОДНОГО воркера. Без неё 4 вкладки бьют по
    # Ozon без остановки, и после ~8-15 быстрых запросов подряд
    # срабатывает антибот-защита - страница отдаётся урезанной, без
    # нужных виджетов, и парсинг падает по таймауту сразу на всех
    # товарах.
    WORKER_DELAY_MIN = 1.5
    WORKER_DELAY_MAX = 3.0
    # ==========================================================
    # CLASSIFIER WORKERS - ОТДЕЛЬНАЯ группа воркеров, НЕ связана с
    # MAX_WORKERS выше. MAX_WORKERS - это браузерные вкладки (сетевой
    # I/O, упирается в антибот Ozon, больше 2 не имеет смысла - Ян
    # проверял вручную). Эта константа - количество ПАРАЛЛЕЛЬНЫХ
    # процессов, которые чистят название/ищут код в словаре
    # (CandidateScorer против ~1500+ товаров, лемматизация pymorphy3) -
    # чистая работа процессора, никакого сетевого ожидания. Именно она
    # реально зависит от количества ядер и её имеет смысл увеличивать
    # отдельно от MAX_WORKERS. Значение 4 - по результату уже
    # проведённого Яном теста (`processors/ozon_pipeline_test.py`,
    # CLASSIFIER_WORKERS=4 "показали лучший результат" на той же
    # машине). При необходимости можно завязать на реальное число ядер
    # (например `max(1, (os.cpu_count() or 4) - 1)`), но фиксированное
    # 4 сознательно оставлено как уже проверенное на практике значение,
    # а не непроверенная формула.
    CLASSIFIER_WORKERS = 4

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
        self.result_path = str(p.with_name(f"{p.stem}_RESULT{p.suffix}"))
        self.decision_logger = DecisionLogger()
        self.card_repository = CardRepository()
        self.knowledge_base = None
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
        # ------------------------------------------------------
        # CLASSIFIER POOL (см. модуль-уровневые _init_classifier_worker/
        # _classify_card выше) - создаётся в _run_async, когда уже
        # известна learning_history. classify_tasks - список активных
        # asyncio-задач классификации, которые нужно дождаться (await
        # asyncio.gather(...)) ПЕРЕД завершением _run_async, иначе
        # финальное сохранение книги/подсчёт статистики могли бы
        # произойти раньше, чем часть карточек реально доклассифицирована.
        # ------------------------------------------------------
        self.classifier_pool = None
        self.classify_tasks = []
    # ==========================================================
    # LOG
    # ==========================================================
    def log(self, text):

        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("ascii", errors="replace").decode("ascii"))

        if self.logger:
            self.logger(text)
    # ==========================================================
    # CACHE
    # ==========================================================
    def get_cached_card(self, url):

        if not url:
            return None

        # 1. Постоянный кэш - карточка прошла полное обучение и
        # подтверждена куратором (LearningRuntime.mark_learning_
        # processed). Проверяем ПЕРВЫМ: это самый надёжный и самый
        # дешёвый источник, и именно сюда попадают карточки,
        # УДАЛЁННЫЕ из card_repository после архивации.
        if self.knowledge_base is not None:

            lean = self.knowledge_base.get(url)

            if lean:
                return lean

        # 2. Временный кэш - карточка уже обрабатывалась в этом или
        # прошлом запуске, но ещё не прошла обучение/подтверждение.
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

    async def async_worker(self, worker_id, page, task_queue, result_queue, engine, context=None, route_handler=None):

        self.log(
            f"[OzonWorker-{worker_id}] "
            f"запущен"
        )
        first_task = True
        # ==================================================
        # СТАРТОВЫЙ РАЗБРОС
        # ==================================================
        startup_delay = worker_id * random.uniform(1.0, 2.0)
        await asyncio.sleep(startup_delay)

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
                    await asyncio.sleep(0.2)
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
                # АНТИБОТ-ПАУЗА (между запросами ОДНОГО воркера)
                # ==================================================
                if not first_task:
                    delay = random.uniform(
                        self.WORKER_DELAY_MIN,
                        self.WORKER_DELAY_MAX,
                    )
                    await asyncio.sleep(delay)
                first_task = False
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
                card = await self.async_parser.parse_url_async(page, url)
                # ==================================================
                # EXCEL TITLE
                # ==================================================
                if excel_name:
                    card.excel_title = excel_name
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

                is_goto_failure = (
                    "goto" in str(exc).lower()
                    or "timeout" in type(exc).__name__.lower()
                )

                if is_goto_failure and context is not None:

                    self.log(
                        f"[OzonWorker-{worker_id}] "
                        f"Вкладка не отвечает - пересоздаю..."
                    )

                    try:
                        await page.close()
                    except Exception:
                        pass

                    try:
                        page = await context.new_page()

                        if route_handler is not None:
                            await page.route("**/*", route_handler)

                        self.log(
                            f"[OzonWorker-{worker_id}] "
                            f"Новая вкладка готова"
                        )
                    except Exception as recreate_exc:
                        self.log(
                            f"[OzonWorker-{worker_id}] "
                            f"Не удалось пересоздать вкладку: "
                            f"{recreate_exc}"
                        )

                await result_queue.put({
                    "row": task[0],
                    "url": task[1],
                    "error": exc,
                    "traceback": traceback.format_exc(),
                })
            finally:

                task_queue.task_done()

    async def _run_async(self, rows_to_process, ws, wb, engine):
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
        # ======================================================
        # CLASSIFIER POOL (CPU, отдельно от браузерных вкладок ниже -
        # см. module-level _init_classifier_worker/_classify_card и
        # комментарий у CLASSIFIER_WORKERS выше)
        # ======================================================
        self.classify_tasks = []
        self.classifier_pool = ProcessPoolExecutor(
            max_workers=self.CLASSIFIER_WORKERS,
            initializer=_init_classifier_worker,
            initargs=(engine.learning_history,),
        )
        self.log(
            f"Пул классификации запущен: "
            f"{self.CLASSIFIER_WORKERS} процесс(ов)"
        )

        context = (self.async_parser.async_context)
        self.log(
            "CDP подключён. "
            "Создаём постоянные вкладки..."
        )
        # ======================================================
        # 4 ПОСТОЯННЫЕ ВКЛАДКИ
        # ======================================================
        worker_count = min(self.MAX_WORKERS, len(rows_to_process))
        # ======================================================
        # ROUTE HANDLER (единственное определение - используется
        # для ВСЕХ вкладок, и существующих, и новых. Раньше был
        # дублирующийся локальный route_handler внутри цикла добора
        # вкладок, из-за чего на новых вкладках регистрировалось
        # ДВА обработчика маршрутов на один и тот же паттерн "**/*" -
        # лишние накладные расходы на каждый сетевой запрос.)
        # ======================================================
        async def route_handler(route):

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
        # ======================================================
        # ПОЛУЧАЕМ УЖЕ СУЩЕСТВУЮЩИЕ ВКЛАДКИ
        # ======================================================
        pages = [
            page
            for page in context.pages
            if not page.is_closed()
        ]
        self.log(f"Существующих вкладок: {len(pages)}")
        # ======================================================
        # ЕСЛИ НЕТ ВКЛАДОК — СОЗДАЁМ ПЕРВУЮ
        # ======================================================
        if not pages:

            page = (await self.async_parser.async_browser.new_page())
            pages.append(page)
        # ======================================================
        # ДОБИРАЕМ ВКЛАДКИ ДО worker_count
        # ======================================================
        while len(pages) < worker_count:

            page = await context.new_page()
            pages.append(page)
            self.log(
                f"[OzonWorker-{len(pages)}] "
                f"Page готова: {page.url}"
            )
            # --------------------------------------------------
            # Пауза между созданием вкладок
            # --------------------------------------------------
            if len(pages) < worker_count:
                await asyncio.sleep(0.5)
        # ======================================================
        # НАСТРАИВАЕМ ВСЕ РАБОЧИЕ ВКЛАДКИ (ровно один route на
        # каждую, включая уже существующие)
        # ======================================================
        for index, page in enumerate(
                pages[:worker_count],
                start=1,
        ):
            await page.route(
                "**/*",
                route_handler,
            )
            self.log(
                f"[OzonWorker-{index}] "
                f"Page готова: {page.url}"
            )
        # ======================================================
        # ЕСЛИ БРАУЗЕР БЫЛ ЗАПУЩЕН С ЛИШНИМИ ВКЛАДКАМИ
        # ======================================================
        if len(pages) > worker_count:

            for page in pages[worker_count:]:
                try:
                    await page.close()
                except Exception:
                    pass

            pages = pages[:worker_count]
        self.log(f"Рабочих вкладок: {len(pages)}")
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
            await task_queue.put(task)
        # ======================================================
        # WORKERS
        # ======================================================
        workers = []

        for index, page in enumerate(pages):
            workers.append(
                asyncio.create_task(
                    self.async_worker(
                        index + 1,
                        page,
                        task_queue,
                        result_queue,
                        engine,
                        context=context,
                        route_handler=route_handler,
                    )
                )
            )
        # ======================================================
        # STOP SIGNAL
        # ======================================================
        for _ in workers:
            await task_queue.put(None)
        # ======================================================
        # RESULTS
        # ======================================================
        completed = 0

        try:
            while (
                    completed
                    < len(rows_to_process)
            ):
                result_data = (await result_queue.get())
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
                    #
                    # Классификация (CPU-работа: очистка/скоринг по
                    # словарю) теперь уходит в отдельный процесс из
                    # self.classifier_pool, а не выполняется здесь же
                    # синхронно - это позволяет браузерным вкладкам
                    # продолжать забирать СЛЕДУЮЩИЕ карточки, пока
                    # предыдущие ещё классифицируются на других ядрах.
                    # Задача отслеживается в self.classify_tasks и
                    # дожидается ниже, ПОСЛЕ основного цикла, чтобы
                    # финальное сохранение/статистика не ушли вперёд
                    # ещё не доклассифицированных карточек.
                    # ==============================================
                    else:

                        card = result_data["card"]

                        self.classify_tasks.append(
                            asyncio.create_task(
                                self._classify_and_apply(
                                    row,
                                    card,
                                    ws,
                                    engine,
                                    wb,
                                )
                            )
                        )
                        # processed_rows/print_progress/save для этой
                        # карточки выполнит сама _classify_and_apply,
                        # когда классификация реально завершится - не
                        # здесь (здесь карточка ещё не классифицирована).
                        continue

                    # ==============================================
                    # PROGRESS (только для CACHE/ERROR/STOP - для
                    # обычной карточки см. _classify_and_apply)
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
                        wb.save(self.result_path)
                        self.log("Файл сохранён")

                finally:
                    result_queue.task_done()

            # ==================================================
            # ЖДЁМ ВСЕ ЕЩЁ НЕЗАВЕРШЁННЫЕ КЛАССИФИКАЦИИ
            #
            # completed выше считает СКАЧАННЫЕ карточки (fetch), а не
            # доклассифицированные - без этого ожидания цикл мог бы
            # выйти, пока часть карточек ещё считается в
            # classifier_pool, и постобработка/финальное сохранение
            # книги ниже (см. run()) не увидели бы их результат.
            # ==================================================
            if self.classify_tasks:
                self.log(
                    f"Ожидание завершения классификации "
                    f"({len(self.classify_tasks)})..."
                )
                await asyncio.gather(
                    *self.classify_tasks,
                    return_exceptions=True,
                )
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
            # ==================================================
            # CLOSE CLASSIFIER POOL
            # ==================================================
            if self.classifier_pool is not None:
                self.classifier_pool.shutdown(wait=True)
                self.classifier_pool = None
    # ==========================================================
    # CLASSIFY (в отдельном процессе) + ПРИМЕНИТЬ РЕЗУЛЬТАТ
    # ==========================================================
    async def _classify_and_apply(self, row, card, ws, engine, wb):
        """Отправляет уже спарсенную card в self.classifier_pool
        (отдельный процесс, чистый CPU - см. module-level
        _classify_card выше), дожидается результата БЕЗ блокировки
        event loop (run_in_executor), и применяет его так же, как
        раньше делал синхронный путь: remember() на ГЛАВНОМ
        DecisionEngine (единственном, который реально сохраняется на
        диск - воркер-процесс звал decide(remember=False) и ничего не
        сохранял), затем apply_result() как обычно."""

        try:
            loop = asyncio.get_running_loop()

            card, result = await loop.run_in_executor(
                self.classifier_pool,
                _classify_card,
                card,
            )

            engine.remember(card, result)

            self.apply_result(
                ws,
                row,
                card,
                result,
            )

        except Exception:

            self.log(
                "Ошибка классификации "
                f"(строка {row}):\n"
                f"{traceback.format_exc()}"
            )

        finally:

            self.processed_rows += 1
            self.print_progress()

            if (
                    self.processed_rows
                    % 20
                    == 0
            ):
                wb.save(self.result_path)
                self.log("Файл сохранён")
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

    def find_last_data_row(self, ws):
        """ws.max_row в openpyxl нередко завышен - он отражает границу
        форматирования листа, а не последнюю реально заполненную
        строку (например, если стиль применён на тысячи строк вперёд
        в шаблоне). Из-за этого apply_restrictions/
        apply_visual_postprocessing красили пустые строки ниже
        реальных данных как "запрещённые/нулевой код".

        Сканируем СНИЗУ ВВЕРХ от ws.max_row и ищем первую строку, где
        есть хоть что-то значимое: наименование (B), код (C) или
        ссылка (D/E)."""

        for row in range(ws.max_row, 1, -1):

            if str(ws[f"B{row}"].value or "").strip():
                return row

            if str(ws[f"C{row}"].value or "").strip():
                return row

            if self.get_url_from_row(ws, row):
                return row

        return 1
    # ==========================================================
    # APPLY CACHE RESULT
    # ==========================================================

    def apply_cached_result(self, ws, row, cached_card):
        description = (
            cached_card.get("display_name")
            or cached_card.get("product")
            or cached_card.get("description")
            or ""
        )
        code = str(
            cached_card.get("code", "")).strip()

        if description:
            ws[f"B{row}"] = description

        ws[f"N{row}"] = cached_card.get("dropdown_group", "") or ""

        if code and code not in ("0", "nan"):
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
    def apply_result(self, ws, row, card, result):
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
        ws[f"M{row}"] = result.material or ""
        # N - факт, на котором реально выбран dropdown-вариант
        # (материал/пол/характеристика: "metal"/"male"/"electric" и
        # т.п.) - нужен постобработке для покраски ячейки кода
        # (см. excel/postprocessing.py::apply_group_colors).
        ws[f"N{row}"] = getattr(result, "dropdown_group", "") or ""
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
        elif getattr(card, "title", "") or getattr(card, "description", ""):
            # Код не присвоен и продукт не определён - но карточка
            # реально спарсилась (название/описание с самой страницы
            # Ozon есть). Пишем ЕГО вместо того, чтобы молча оставить
            # то, что уже было в B (часто - просто старое/пустое
            # значение) - куратор сразу видит, что реально написано
            # на странице, и может понять, какой код/алиас нужен,
            # вместо пустой догадки.
            ws[f"B{row}"] = (
                getattr(card, "title", "")
                or getattr(card, "description", "")
            )
        else:
            ws[f"B{row}"] = original
        # ------------------------------------------------------
        # C
        # ------------------------------------------------------
        if result.code:
            try:
                ws[f"C{row}"] = int(result.code)
            except ValueError:
                ws[f"C{row}"] = (result.code)
        elif result.review:
            # Явно очищаем ячейку (а не оставляем как есть), иначе
            # при повторной обработке той же книги старый код от
            # прошлого запуска (в т.ч. неверный, ранее угаданный
            # через DROPDOWN_FIRST, или конкретный код одного из
            # нескольких равнозначных товаров при мульти-товарном
            # листинге - см. product_resolver.py::
            # _clear_ambiguous_multi_product_code) мог бы молча
            # остаться в ячейке, не будучи ни правильным, ни явно
            # помеченным как спорный. result.review здесь означает
            # "код умышленно оставлен пустым, требуется ручной
            # выбор" - для полного провала (NO_CANDIDATES) это тоже
            # верно и ничего не меняет по сравнению с прошлым
            # поведением.
            ws[f"C{row}"] = None
        # ------------------------------------------------------
        # Комментарий к ячейке кода со списком вариантов, среди
        # которых не удалось однозначно выбрать (result.alternatives,
        # см. resolver/dropdown_resolver.py, случай "4. Ничего не
        # определили"). Раньше эта информация писалась ТОЛЬКО в
        # консольный лог и терялась после закрытия программы - в
        # самом Excel куратор её не видел вообще (в отличие от
        # старого пути engines/result_engine.py::set_comment, который
        # для обычного - не Ozon-авто - режима уже так делает; здесь
        # того же не было). Комментарий вешаем даже когда C{row}
        # пустая (result.code == "") - именно в этом и есть смысл:
        # ячейка пустая и явно требует ручного выбора одного из
        # перечисленных кодов, вместо того чтобы куратор видел
        # неверный, но правдоподобный код без пояснений.
        # ------------------------------------------------------
        alternatives = getattr(result, "alternatives", None) or {}

        if result.review and alternatives:
            comment_text = "Выбрать код вручную:\n" + "\n".join(
                f"{code} — {name}"
                for code, name in alternatives.items()
            )
            ws[f"C{row}"].comment = Comment(comment_text, "Classifier")
        # ------------------------------------------------------
        # ДОБАВЛЕНО: result.review видимо ТОЛЬКО через комментарий
        # (см. выше) - легко пропустить при просмотре сотен строк,
        # особенно когда result.code при этом всё же проставлен (код
        # выглядит как обычное уверенное значение - разбор реального
        # кейса SPDIF-разветвителя, Уверенность: 50%, куратор узнал о
        # спорности только из консольного лога). Подсвечиваем строку
        # заливкой + курсивом сразу в самой таблице - не только когда
        # C{row} пустая, но и когда код проставлен, просто неуверенно.
        # ------------------------------------------------------
        if result.review:
            for col in ("B", "C"):
                cell = ws[f"{col}{row}"]
                cell.fill = REVIEW_FILL
                cell.font = REVIEW_FONT
        # ------------------------------------------------------
        # Statistics
        # ------------------------------------------------------
        if result.code:

            self.found_count += 1
            self.log(f"Описание: {result.dropdown}")
            self.log(f"Товар: {result.product}")
            self.log(f"Материал: {result.material}")
            self.log(f"Код: {result.code}")
            self.log(f"Источник: {result.source}")
            self.log(
                f"Уверенность: "
                f"{result.confidence}%"
            )
            if result.review:
                self.log("⚠ Требуется проверка")
        elif result.review and alternatives:
            # Код умышленно оставлен пустым - либо товар определён
            # верно, но не удалось однозначно выбрать вариант/код
            # (dropdown, source="DROPDOWN_UNRESOLVED" - материал/пол/
            # назначение не распознаны в тексте карточки), либо
            # карточка описывает сразу НЕСКОЛЬКО разных реальных
            # товаров с одинаковым топ-score (source="PRODUCTS",
            # winner.reason="AMBIGUOUS" - см. product_resolver.py::
            # _clear_ambiguous_multi_product_code). Раньше в обоих
            # случаях молча проставлялся код одного произвольно
            # выбранного варианта/товара, теперь честно помечается
            # как неопределённое. См.
            # products-dict-gradation-audit.md, обновление (7).
            self.not_found_count += 1
            self.log(f"Описание: {result.product}")
            self.log(
                "Код не определён однозначно среди "
                f"{len(alternatives)} вариантов - требуется ручной "
                "выбор (см. комментарий к ячейке кода)"
            )
            for alt_code, alt_name in alternatives.items():
                self.log(f"    {alt_code} — {alt_name}")
        else:

            self.not_found_count += 1
            self.log(
                f"Описание: "
                f"{result.product}"
            )
            self.log("Код не найден")
    # ==========================================================
    # RUN
    # ==========================================================
    def run(self):

        self.start_time = time.time()
        self.log("Открытие Excel...")
        wb = openpyxl.load_workbook(self.excel_path)
        ws = wb.active
        rows_to_process = []
        # ==========================================================
        # СОБИРАЕМ СТРОКИ
        # ==========================================================
        for row in range(2, ws.max_row + 1):

            url = self.get_url_from_row(ws, row)
            current_code = ws[f"C{row}"].value

            if self.skip_filled:

                if current_code not in (None, "", 0):
                    continue

            if url:
                excel_name = str(ws[f"B{row}"].value or "").strip()
                rows_to_process.append((row, url, excel_name))
        # ==========================================================
        # LIMIT
        # ==========================================================
        if self.limit:
            rows_to_process = (rows_to_process[ :self.limit])
        self.total_rows = len(rows_to_process)
        self.log(
            f"Всего строк: "
            f"{self.total_rows}"
        )

        if not rows_to_process:

            wb.save(self.result_path)
            self.print_summary()

            return
        # ==========================================================
        # LEARNING HISTORY
        # ==========================================================
        learning_history = (load_learning_history(self.excel_path))
        engine = DecisionEngine(learning_history)
        self.card_repository = engine.knowledge.card_repository

        # Постоянный кэш карточек, прошедших полное обучение и
        # подтверждение куратором (см. get_cached_card ниже) -
        # LearningRuntime.mark_learning_processed() архивирует сюда и
        # УДАЛЯЕТ карточку из card_repository/runtime_cards.json,
        # поэтому get_cached_card обязан проверять оба источника.
        self.knowledge_base = engine.knowledge.knowledge_base
        # ==========================================================
        # ASYNC PARSING
        # ==========================================================
        try:

            asyncio.run(self._run_async(rows_to_process, ws, wb, engine))

            # ------------------------------------------------------
            # ПОСТОБРАБОТКА
            # Покраска строк по запрещённым/разрешённым префиксам
            # кода.
            # ------------------------------------------------------
            self.log("Проверка ограничений...")

            postprocess_last_row = self.find_last_data_row(ws)

            visual_stats = apply_visual_postprocessing(
                ws,
                code_col_idx=3,       # колонка C
                max_row=postprocess_last_row,
            )

            self.log(
                f"Постобработка: "
                f"красных={visual_stats['red']}, "
                f"зелёных={visual_stats['green']}"
            )

            # Покраска ячейки кода по факту (материал/пол/
            # характеристика), на котором реально выбран dropdown-
            # вариант - для наглядности, тем же справочником цветов,
            # что уже используется в ручном режиме
            # (modules/dropdown_manager.py).
            group_stats = apply_group_colors(
                ws,
                code_col_idx=3,        # колонка C
                group_col_idx=14,      # колонка N
                max_row=postprocess_last_row,
            )

            self.log(
                f"Покраска по факту: "
                f"покрашено={group_stats['colored']}"
            )

        except Exception:

            self.log(traceback.format_exc())

            raise
        finally:

            # Финальный flush - без него "хвост" карточек после
            # последней контрольной точки (DecisionEngine сбрасывает
            # кэш на диск каждые 20 карточек) никогда не попадает в
            # storage/runtime_cards.json
            engine.knowledge.card_repository.flush()

            wb.save(self.result_path)
        self.print_summary()
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
        self.log("ОБРАБОТКА ЗАВЕРШЕНА")
        self.log(f"Всего: {self.total_rows}")
        self.log(f"Найдено: {self.found_count}")
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
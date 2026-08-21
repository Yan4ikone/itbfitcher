import copy
import json
import os
import queue
import threading
import time
import traceback

from concurrent.futures import ProcessPoolExecutor

from learning.importer import load_learning_history
from engines.decision_engine import DecisionEngine
from models.card_builder import build_product_card

from ozon_excel_processor import OzonExcelProcessor


# =============================================================================
# CONFIG
# =============================================================================

INPUT_FILE = "input.xlsx"

# Browser workers.
# Мы уже знаем, что 2 browser workers работают стабильно.
# Поэтому сначала тестируем именно 2.
BROWSER_WORKERS = 2

# CPU classifier processes.
# По предыдущему тесту 4 показали лучший результат.
CLASSIFIER_WORKERS = 4

# Сколько карточек прогонять.
# None = весь Excel.
LIMIT = None

# Как часто писать прогресс.
PROGRESS_EVERY = 10

# Результаты теста.
RESULT_JSON = "ozon_pipeline_test_results.json"
LOG_FILE = "ozon_pipeline_test.log"

# Размер очереди между parser и classifier.
# Ограничение нужно, чтобы огромные HTML/parsed dict не
# накапливались бесконечно в RAM.
CLASSIFIER_QUEUE_SIZE = CLASSIFIER_WORKERS * 4


# =============================================================================
# LOGGER
# =============================================================================

class Logger:

    def __init__(self, filename):

        self.filename = filename

        with open(
            self.filename,
            "w",
            encoding="utf-8",
        ):
            pass

        self.lock = threading.Lock()

    def log(self, message=""):

        with self.lock:

            print(
                message,
                flush=True,
            )

            with open(
                self.filename,
                "a",
                encoding="utf-8",
            ) as f:

                f.write(
                    str(message) + "\n"
                )


log = Logger(LOG_FILE)


# =============================================================================
# CLASSIFIER PROCESS STATE
# =============================================================================

_worker_engine = None


def init_classifier_worker(
    learning_history,
):
    """
    Один DecisionEngine на один процесс.

    Это принципиально важно:
    DecisionEngine не создаётся на каждую карточку.
    """

    global _worker_engine

    _worker_engine = DecisionEngine(
        learning_history
    )


# =============================================================================
# RESULT EXTRACTION
# =============================================================================

def extract_result(result):

    if result is None:

        return {
            "product": "",
            "display_name": "",
            "dropdown": "",
            "code": "",
            "source": "",
            "confidence": None,
            "review": False,
        }

    return {
        "product":
            getattr(
                result,
                "product",
                "",
            ) or "",

        "display_name":
            (
                getattr(
                    result,
                    "display_name",
                    "",
                )
                or
                getattr(
                    result,
                    "dropdown",
                    "",
                )
                or ""
            ),

        "dropdown":
            getattr(
                result,
                "dropdown",
                "",
            ) or "",

        "code":
            getattr(
                result,
                "code",
                "",
            ) or "",

        "source":
            getattr(
                result,
                "source",
                "",
            ) or "",

        "confidence":
            getattr(
                result,
                "confidence",
                None,
            ),

        "review":
            bool(
                getattr(
                    result,
                    "review",
                    False,
                )
            ),
    }


# =============================================================================
# CLASSIFIER TASK
# =============================================================================

def classify_one(item):
    """
    Выполняется внутри отдельного classifier process.

    ВАЖНО:
    remember=False.

    Дочерние процессы НЕ пишут runtime_cards.json.
    Это будет делать главный процесс после получения результата.
    """

    global _worker_engine

    index = item["index"]
    row_number = item["row_number"]
    url = item["url"]
    parsed = item["parsed"]

    started = time.perf_counter()

    try:

        parsed_local = copy.deepcopy(
            parsed
        )

        card = build_product_card(
            url,
            parsed_local,
            raw_text=parsed_local.get(
                "description",
                "",
            ),
        )

        result = _worker_engine.decide(
            card,
            remember=False,
        )

        elapsed = (
            time.perf_counter()
            - started
        )

        return {
            "success": True,

            "index": index,

            "row_number":
                row_number,

            "url":
                url,

            "parsed":
                parsed,

            "elapsed":
                elapsed,

            **extract_result(result),

            "error":
                "",
        }

    except Exception as exc:

        elapsed = (
            time.perf_counter()
            - started
        )

        return {
            "success": False,

            "index":
                index,

            "row_number":
                row_number,

            "url":
                url,

            "parsed":
                parsed,

            "elapsed":
                elapsed,

            "product":
                "",

            "display_name":
                "",

            "dropdown":
                "",

            "code":
                "",

            "source":
                "",

            "confidence":
                None,

            "review":
                False,

            "error":
                repr(exc),

            "traceback":
                traceback.format_exc(),
        }


# =============================================================================
# PIPELINE
# =============================================================================

class OzonPipelineTest:

    def __init__(self):

        self.processor = None

        self.executor = None

        self.classifier_queue = queue.Queue(
            maxsize=CLASSIFIER_QUEUE_SIZE
        )

        self.classifier_result_queue = queue.Queue()

        self.stop_event = threading.Event()

        self.submit_thread = None

        self.result_thread = None

        self.submitted = 0

        self.classified = 0

        self.errors = 0

        self.parser_ok = 0

        self.parser_errors = 0

        self.start_time = None

        self.classify_times = []

        self.results = []

        self.lock = threading.Lock()

        self.all_submitted = threading.Event()

        self.classifier_finished = threading.Event()


    # =========================================================================
    # SUBMIT CLASSIFIER
    # =========================================================================

    def submit_loop(self):

        log.log(
            "[PIPELINE] Classifier submit thread START"
        )

        while True:

            try:

                item = self.classifier_queue.get(
                    timeout=0.2
                )

            except queue.Empty:

                if (
                    self.all_submitted.is_set()
                    and
                    self.classifier_queue.empty()
                ):
                    break

                continue

            try:

                future = self.executor.submit(
                    classify_one,
                    item,
                )

                future.add_done_callback(
                    self.classifier_done
                )

                with self.lock:
                    self.submitted += 1

            except Exception as exc:

                log.log(
                    "[PIPELINE] "
                    f"SUBMIT ERROR: {repr(exc)}"
                )

                self.classifier_result_queue.put({
                    "success": False,
                    "index":
                        item["index"],
                    "row_number":
                        item["row_number"],
                    "url":
                        item["url"],
                    "parsed":
                        item["parsed"],
                    "elapsed":
                        0,
                    "product":
                        "",
                    "display_name":
                        "",
                    "dropdown":
                        "",
                    "code":
                        "",
                    "source":
                        "",
                    "confidence":
                        None,
                    "review":
                        False,
                    "error":
                        repr(exc),
                    "traceback":
                        traceback.format_exc(),
                })

            finally:

                self.classifier_queue.task_done()

        log.log(
            "[PIPELINE] Classifier submit thread STOP"
        )


    # =========================================================================
    # FUTURE CALLBACK
    # =========================================================================

    def classifier_done(
        self,
        future,
    ):

        try:

            result = future.result()

        except Exception as exc:

            result = {
                "success": False,
                "index": -1,
                "row_number": -1,
                "url": "",
                "parsed": {},
                "elapsed": 0,
                "product": "",
                "display_name": "",
                "dropdown": "",
                "code": "",
                "source": "",
                "confidence": None,
                "review": False,
                "error": repr(exc),
                "traceback": traceback.format_exc(),
            }

        self.classifier_result_queue.put(
            result
        )


    # =========================================================================
    # RESULT LOOP
    # =========================================================================

    def result_loop(self):

        log.log(
            "[PIPELINE] Result thread START"
        )

        while True:

            try:

                result = (
                    self.classifier_result_queue.get(
                        timeout=0.2
                    )
                )

            except queue.Empty:

                if (
                    self.classifier_finished.is_set()
                    and
                    self.classifier_result_queue.empty()
                ):
                    break

                continue

            try:

                self.handle_classified_result(
                    result
                )

            except Exception:

                log.log(
                    "[PIPELINE] "
                    "RESULT ERROR:"
                )

                log.log(
                    traceback.format_exc()
                )

            finally:

                self.classifier_result_queue.task_done()

        log.log(
            "[PIPELINE] Result thread STOP"
        )


    # =========================================================================
    # CLASSIFIED RESULT
    # =========================================================================

    def handle_classified_result(
        self,
        result,
    ):

        with self.lock:

            self.classified += 1

            if not result["success"]:

                self.errors += 1

            else:

                self.classify_times.append(
                    result["elapsed"]
                )

        self.results.append(
            result
        )

        # ---------------------------------------------------------------------
        # Здесь ПОКА только считаем throughput.
        #
        # Excel мы специально не трогаем на этом этапе.
        #
        # После успешного теста сюда перенесём:
        #
        # 1. write_result()
        # 2. card_repository.remember()
        # 3. checkpoint
        #
        # ---------------------------------------------------------------------

        count = self.classified

        if (
            count % PROGRESS_EVERY == 0
            or
            count == self.parser_ok
        ):

            elapsed = (
                time.perf_counter()
                - self.start_time
            )

            speed = (
                count / elapsed
                if elapsed > 0
                else 0
            )

            log.log(
                f"[CLASSIFIER] "
                f"{count} classified | "
                f"{speed:.3f} card/s | "
                f"{speed * 3600:,.0f}/hour"
            )


    # =========================================================================
    # FEED PARSED CARD
    # =========================================================================

    def feed_parser_result(
        self,
        result,
        index,
    ):

        status = result.get(
            "Parser Status"
        )

        if status != "OK":

            with self.lock:
                self.parser_errors += 1

            return

        parsed = result.get(
            "_parsed_raw"
        )

        if not parsed:

            with self.lock:
                self.parser_errors += 1

            return

        with self.lock:
            self.parser_ok += 1

        item = {
            "index":
                index,

            "row_number":
                result["row_number"],

            "url":
                (
                    result.get(
                        "_final_url"
                    )
                    or
                    result.get(
                        "url"
                    )
                    or ""
                ),

            "parsed":
                parsed,
        }

        # ---------------------------------------------------------------------
        # ВАЖНО:
        #
        # put() блокируется, если classifier не успевает.
        #
        # Это создаёт естественный backpressure:
        #
        # Browser → Parser → Queue → Classifier
        #
        # RAM не раздувается.
        # ---------------------------------------------------------------------

        self.classifier_queue.put(
            item
        )


    # =========================================================================
    # RUN
    # =========================================================================

    def run(self):

        self.start_time = time.perf_counter()

        log.log("")
        log.log("=" * 100)
        log.log("OZON PIPELINE TEST")
        log.log("=" * 100)

        log.log(
            f"Browser workers:     "
            f"{BROWSER_WORKERS}"
        )

        log.log(
            f"Classifier workers:  "
            f"{CLASSIFIER_WORKERS}"
        )

        log.log(
            f"Input:               "
            f"{INPUT_FILE}"
        )

        log.log("=" * 100)

        # ---------------------------------------------------------------------
        # LEARNING HISTORY
        # ---------------------------------------------------------------------

        learning_history = load_learning_history(
            INPUT_FILE
        )

        # ---------------------------------------------------------------------
        # CLASSIFIER POOL
        # ---------------------------------------------------------------------

        log.log(
            "[INIT] Starting classifier pool..."
        )

        self.executor = ProcessPoolExecutor(
            max_workers=CLASSIFIER_WORKERS,
            initializer=init_classifier_worker,
            initargs=(
                learning_history,
            ),
        )

        log.log(
            "[INIT] ✓ Classifier pool started"
        )

        # ---------------------------------------------------------------------
        # SUBMIT THREAD
        # ---------------------------------------------------------------------

        self.submit_thread = threading.Thread(
            target=self.submit_loop,
            name="ClassifierSubmit",
            daemon=True,
        )

        self.submit_thread.start()

        # ---------------------------------------------------------------------
        # RESULT THREAD
        # ---------------------------------------------------------------------

        self.result_thread = threading.Thread(
            target=self.result_loop,
            name="ClassifierResult",
            daemon=True,
        )

        self.result_thread.start()

        # ---------------------------------------------------------------------
        # OzonExcelProcessor
        #
        # ВАЖНО:
        # Используем существующий browser/parser.
        # Не копируем его сюда.
        # ---------------------------------------------------------------------

        self.processor = OzonExcelProcessor(
            input_file=INPUT_FILE,
            output_file=None,
            workers=BROWSER_WORKERS,
        )

        self.processor.start_time = time.perf_counter()

        self.processor.open_excel()
        self.processor.read_urls()

        if self.processor.total_urls == 0:

            raise RuntimeError(
                "Нет URL для обработки."
            )

        log.log(
            f"[EXCEL] URLs: "
            f"{self.processor.total_urls}"
        )

        # ---------------------------------------------------------------------
        # START BROWSER WORKERS
        # ---------------------------------------------------------------------

        self.processor.worker_threads = []

        for worker_id in range(
            1,
            BROWSER_WORKERS + 1,
        ):

            thread = threading.Thread(
                target=self.processor.worker,
                args=(worker_id,),
                name=f"OzonWorker-{worker_id}",
                daemon=True,
            )

            self.processor.worker_threads.append(
                thread
            )

            thread.start()

        # ---------------------------------------------------------------------
        # IMPORTANT
        #
        # Нам нужен parser result, но НЕ старый writer,
        # который складывает всё в phase1_results.
        #
        # Поэтому здесь запускаем отдельный lightweight collector,
        # который читает processor.result_queue.
        # ---------------------------------------------------------------------

        parser_collector = threading.Thread(
            target=self.collect_parser_results,
            name="ParserCollector",
            daemon=True,
        )

        parser_collector.start()

        # ---------------------------------------------------------------------
        # WAIT BROWSER
        # ---------------------------------------------------------------------

        for thread in self.processor.worker_threads:

            thread.join()

        self.processor.work_queue.join()

        parser_collector.join()

        # ---------------------------------------------------------------------
        # Больше карточек от parser не будет.
        # ---------------------------------------------------------------------

        self.all_submitted.set()

        self.classifier_queue.join()

        self.submit_thread.join()

        # ---------------------------------------------------------------------
        # Все submitted futures должны завершиться.
        # ---------------------------------------------------------------------

        self.executor.shutdown(
            wait=True
        )

        self.classifier_finished.set()

        self.classifier_result_queue.join()

        self.result_thread.join()

        # ---------------------------------------------------------------------
        # SHUTDOWN PARSER POOL
        # ---------------------------------------------------------------------

        try:

            self.processor.parser_pool.shutdown(
                wait=True
            )

        except Exception:

            pass

        # ---------------------------------------------------------------------
        # FINAL
        # ---------------------------------------------------------------------

        elapsed = (
            time.perf_counter()
            - self.start_time
        )

        total = (
            self.processor.total_urls
        )

        speed = (
            total / elapsed
            if elapsed > 0
            else 0
        )

        log.log("")
        log.log("=" * 100)
        log.log("ИТОГ OZON PIPELINE TEST")
        log.log("=" * 100)

        log.log(
            f"Всего URL:             "
            f"{total}"
        )

        log.log(
            f"Parser OK:             "
            f"{self.parser_ok}"
        )

        log.log(
            f"Parser ERROR:          "
            f"{self.parser_errors}"
        )

        log.log(
            f"Classifier OK:         "
            f"{self.classified - self.errors}"
        )

        log.log(
            f"Classifier ERROR:      "
            f"{self.errors}"
        )

        log.log("")

        log.log(
            f"Общее время:           "
            f"{elapsed:.2f} сек"
        )

        log.log(
            f"Общая скорость:        "
            f"{speed:.3f} card/s"
        )

        log.log(
            f"В час:                 "
            f"{speed * 3600:,.0f}"
        )

        log.log(
            f"За 24 часа:            "
            f"{speed * 86400:,.0f}"
        )

        log.log("=" * 100)

        # ---------------------------------------------------------------------
        # SAVE RESULTS
        # ---------------------------------------------------------------------

        output = {
            "total": total,
            "parser_ok":
                self.parser_ok,
            "parser_errors":
                self.parser_errors,
            "classifier_ok":
                self.classified - self.errors,
            "classifier_errors":
                self.errors,
            "elapsed":
                elapsed,
            "speed":
                speed,
            "per_hour":
                speed * 3600,
            "per_day":
                speed * 86400,
            "browser_workers":
                BROWSER_WORKERS,
            "classifier_workers":
                CLASSIFIER_WORKERS,
            "results":
                self.results,
        }

        with open(
            RESULT_JSON,
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                output,
                f,
                ensure_ascii=False,
                indent=2,
            )

        log.log(
            f"[SAVE] ✓ {RESULT_JSON}"
        )

        log.log(
            f"[SAVE] ✓ {LOG_FILE}"
        )

    # =========================================================================
    # PARSER COLLECTOR
    # =========================================================================

    def collect_parser_results(self):

        log.log(
            "[PIPELINE] Parser collector START"
        )

        index = 0

        while True:

            try:

                result = (
                    self.processor.result_queue.get(
                        timeout=0.2
                    )
                )

            except queue.Empty:

                if (
                    self.processor.work_queue.unfinished_tasks
                    == 0
                    and
                    all(
                        not t.is_alive()
                        for t in self.processor.worker_threads
                    )
                    and
                    self.processor.result_queue.empty()
                ):

                    break

                continue

            try:

                status = result.get(
                    "Parser Status"
                )

                if status == "RETRY":

                    # Старый worker сам должен положить
                    # повторную задачу обратно в work_queue.
                    continue

                index += 1

                self.feed_parser_result(
                    result,
                    index,
                )

            except Exception:

                log.log(
                    "[PIPELINE] "
                    "Parser collector ERROR:"
                )

                log.log(
                    traceback.format_exc()
                )

            finally:

                self.processor.result_queue.task_done()

        log.log(
            "[PIPELINE] Parser collector STOP"
        )


# =============================================================================
# MAIN
# =============================================================================

def main():

    import multiprocessing

    multiprocessing.freeze_support()

    pipeline = OzonPipelineTest()

    pipeline.run()


if __name__ == "__main__":

    main()
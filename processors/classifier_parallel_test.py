import copy
import json
import os
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path


from learning.importer import load_learning_history
from engines.decision_engine import DecisionEngine
from models.card_builder import build_product_card


# =============================================================================
# CONFIG
# =============================================================================

INPUT_FILE = "input.xlsx"

# Проверяем настоящее multiprocessing.
WORKER_COUNTS = [1, 2, 3, 4]

# None = все карточки.
LIMIT = None

SHOW_PROGRESS = True

# Показывать успешные результаты поштучно.
SHOW_EACH_RESULT = False

# Сколько ошибок подробно печатать для каждого теста.
SHOW_ERROR_DETAILS = 10

RESULT_JSON = "classifier_parallel_test_results.json"
LOG_FILE = "classifier_parallel_test.log"

PHASE1_FILE = "ozon_phase1_results.json"


# =============================================================================
# LOGGER
# =============================================================================

class Logger:

    def __init__(self, filename):

        self.filename = Path(filename)

        self.filename.write_text(
            "",
            encoding="utf-8",
        )

    def log(self, message=""):

        message = str(message)

        print(
            message,
            flush=True,
        )

        with self.filename.open(
            "a",
            encoding="utf-8",
        ) as f:

            f.write(
                message + "\n"
            )


log = Logger(LOG_FILE)


# =============================================================================
# PHASE 1
# =============================================================================

def load_phase1_from_json(filename):

    path = Path(filename)

    if not path.exists():

        return None

    log.log(
        f"[LOAD] Найден сохранённый PHASE 1: {path}"
    )

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if not isinstance(data, list):

            raise RuntimeError(
                "PHASE1 JSON должен содержать список."
            )

        log.log(
            f"[LOAD] Загружено карточек: {len(data)}"
        )

        return data

    except Exception:

        log.log(
            "[LOAD] ✗ Ошибка чтения PHASE 1 JSON:"
        )

        log.log(
            traceback.format_exc()
        )

        return None


def save_phase1_to_json(items, filename):

    path = Path(filename)

    log.log(
        f"[SAVE] Сохраняем PHASE 1: {path}"
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            items,
            f,
            ensure_ascii=False,
            indent=2,
        )

    log.log(
        f"[SAVE] ✓ Сохранено карточек: {len(items)}"
    )


def get_phase1_results():

    phase1 = load_phase1_from_json(
        PHASE1_FILE
    )

    if phase1 is not None:

        return phase1

    log.log("")
    log.log("=" * 100)
    log.log("PHASE 1 DATA НЕ НАЙДЕНА")
    log.log("=" * 100)

    log.log(
        "Запускаем существующий OzonExcelProcessor "
        "только для получения parsed-карточек."
    )

    log.log("=" * 100)
    log.log("")

    from ozon_excel_processor import OzonExcelProcessor

    processor = OzonExcelProcessor(
        input_file=INPUT_FILE,
        output_file=None,
        workers=2,
    )

    processor.start_time = time.perf_counter()

    processor.open_excel()
    processor.read_urls()

    if processor.total_urls == 0:

        raise RuntimeError(
            "В input.xlsx не найдено новых Ozon URL."
        )

    log.log(
        f"[PHASE 1] URL: {processor.total_urls}"
    )

    import threading

    processor.worker_threads = []

    for worker_id in range(
        1,
        processor.workers + 1,
    ):

        thread = threading.Thread(
            target=processor.worker,
            args=(worker_id,),
            name=f"OzonWorker-{worker_id}",
            daemon=True,
        )

        processor.worker_threads.append(
            thread
        )

        thread.start()

    processor.writer_thread = threading.Thread(
        target=processor.writer,
        name="ExcelWriter",
        daemon=True,
    )

    processor.writer_thread.start()

    for thread in processor.worker_threads:

        thread.join()

    processor.work_queue.join()
    processor.result_queue.join()

    processor.writer_thread.join()

    processor.parser_pool.shutdown(
        wait=True
    )

    phase1_elapsed = (
        time.perf_counter()
        - processor.start_time
    )

    log.log("")
    log.log(
        f"[PHASE 1] ✓ Завершена: "
        f"{phase1_elapsed:.2f} сек"
    )

    log.log(
        f"[PHASE 1] Карточек: "
        f"{len(processor.phase1_results)}"
    )

    phase1 = processor.phase1_results

    try:

        if processor.wb:

            processor.wb.close()

    except Exception:

        pass

    save_phase1_to_json(
        phase1,
        PHASE1_FILE,
    )

    return phase1


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
            )
            or "",

        "display_name":
            (
                getattr(
                    result,
                    "display_name",
                    "",
                )
                or getattr(
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
            )
            or "",

        "code":
            getattr(
                result,
                "code",
                "",
            )
            or "",

        "source":
            getattr(
                result,
                "source",
                "",
            )
            or "",

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
# SINGLE CLASSIFICATION
# =============================================================================

def classify_one(
    item,
    decision_engine,
):

    index = item["_test_index"]

    row_number = item.get(
        "row_number",
        index,
    )

    url = item.get(
        "url",
        "",
    )

    parsed = item.get(
        "parsed",
        {},
    )

    started = time.perf_counter()

    try:

        # ------------------------------------------------------------------
        # ВАЖНО:
        #
        # Каждый процесс получает свою копию parsed.
        # Никаких общих mutable-объектов между процессами.
        # ------------------------------------------------------------------

        parsed_local = copy.deepcopy(
            parsed
        )

        # ------------------------------------------------------------------
        # BUILD CARD
        # ------------------------------------------------------------------

        card = build_product_card(
            url,
            parsed_local,
            raw_text=parsed_local.get(
                "description",
                "",
            ),
        )

        # ------------------------------------------------------------------
        # DECISION ENGINE
        #
        # remember=False специально для теста.
        #
        # Мы НЕ хотим, чтобы 4 процесса одновременно писали
        # в storage/runtime_cards.json.
        # ------------------------------------------------------------------

        result = decision_engine.decide(
            card,
            remember=False,
        )

        elapsed = (
            time.perf_counter()
            - started
        )

        extracted = extract_result(
            result
        )

        if SHOW_EACH_RESULT:

            log.log(
                f"[OK] #{index} "
                f"{url}"
            )

            log.log(
                f"     PRODUCT: "
                f"{extracted['product']}"
            )

            log.log(
                f"     CODE: "
                f"{extracted['code']}"
            )

            log.log(
                f"     TIME: "
                f"{elapsed:.3f}s"
            )

        return {

            "success": True,

            "index":
                index,

            "row_number":
                row_number,

            "url":
                url,

            "elapsed":
                elapsed,

            **extracted,

            "error":
                "",

            "traceback":
                "",
        }

    except Exception as exc:

        elapsed = (
            time.perf_counter()
            - started
        )

        tb = traceback.format_exc()

        return {

            "success": False,

            "index":
                index,

            "row_number":
                row_number,

            "url":
                url,

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
                tb,
        }


# =============================================================================
# PROCESS WORKER
# =============================================================================

_worker_engine = None


def init_worker(
    learning_history,
):

    global _worker_engine

    worker_pid = os.getpid()

    try:

        log_message = (
            f"[PROCESS INIT] "
            f"PID={worker_pid} "
            f"создание DecisionEngine..."
        )

        print(
            log_message,
            flush=True,
        )

        _worker_engine = DecisionEngine(
            learning_history
        )

        print(
            f"[PROCESS INIT] "
            f"PID={worker_pid} "
            f"✓ DecisionEngine готов",
            flush=True,
        )

    except Exception:

        print(
            f"[PROCESS INIT] "
            f"PID={worker_pid} "
            f"✗ DecisionEngine ERROR",
            flush=True,
        )

        print(
            traceback.format_exc(),
            flush=True,
        )

        raise


# =============================================================================
# CLASSIFY BATCH
# =============================================================================

def classify_batch(
    items,
):

    global _worker_engine

    pid = os.getpid()

    if _worker_engine is None:

        raise RuntimeError(
            f"Worker PID={pid}: "
            f"DecisionEngine не инициализирован"
        )

    results = []

    for item in items:

        result = classify_one(
            item,
            _worker_engine,
        )

        results.append(
            result
        )

    return results


# =============================================================================
# SPLIT WORK
# =============================================================================

def split_items(
    items,
    workers,
):

    chunks = [
        []
        for _ in range(workers)
    ]

    for index, item in enumerate(items):

        chunks[
            index % workers
        ].append(item)

    return chunks


# =============================================================================
# RESULT COMPARISON
# =============================================================================

def build_result_map(
    results,
):

    return {
        item["index"]: item
        for item in results
    }


def compare_results(
    baseline_results,
    parallel_results,
):

    baseline = build_result_map(
        baseline_results
    )

    parallel = build_result_map(
        parallel_results
    )

    differences = []

    fields = (
        "success",
        "product",
        "display_name",
        "code",
        "source",
        "confidence",
        "review",
    )

    for index, base in baseline.items():

        other = parallel.get(
            index
        )

        if other is None:

            differences.append({
                "index":
                    index,

                "type":
                    "MISSING",
            })

            continue

        for field in fields:

            if (
                base.get(field)
                != other.get(field)
            ):

                differences.append({

                    "index":
                        index,

                    "url":
                        base.get(
                            "url"
                        ),

                    "field":
                        field,

                    "baseline":
                        base.get(
                            field
                        ),

                    "parallel":
                        other.get(
                            field
                        ),
                })

    return differences


# =============================================================================
# STATISTICS
# =============================================================================

def percentile(
    values,
    q,
):

    if not values:

        return 0

    if len(values) == 1:

        return values[0]

    position = (
        len(values) - 1
    ) * q

    lower = int(
        position
    )

    upper = min(
        lower + 1,
        len(values) - 1,
    )

    weight = (
        position - lower
    )

    return (
        values[lower]
        * (1 - weight)
        +
        values[upper]
        * weight
    )


def calculate_stats(
    results,
    elapsed,
):

    total = len(
        results
    )

    successful = sum(
        1
        for r in results
        if r["success"]
    )

    errors = (
        total
        - successful
    )

    success_times = [
        r["elapsed"]
        for r in results
        if r["success"]
    ]

    error_times = [
        r["elapsed"]
        for r in results
        if not r["success"]
    ]

    if success_times:

        avg = (
            sum(success_times)
            / len(success_times)
        )

        sorted_times = sorted(
            success_times
        )

        p50 = percentile(
            sorted_times,
            0.50,
        )

        p90 = percentile(
            sorted_times,
            0.90,
        )

        p99 = percentile(
            sorted_times,
            0.99,
        )

        maximum = max(
            sorted_times
        )

    else:

        avg = 0
        p50 = 0
        p90 = 0
        p99 = 0
        maximum = 0

    speed = (
        total / elapsed
        if elapsed > 0
        else 0
    )

    return {

        "total":
            total,

        "successful":
            successful,

        "errors":
            errors,

        "elapsed":
            elapsed,

        "speed":
            speed,

        "per_hour":
            speed * 3600,

        "per_day":
            speed * 86400,

        "avg_card_time":
            avg,

        "p50":
            p50,

        "p90":
            p90,

        "p99":
            p99,

        "max":
            maximum,

        "error_avg_time":
            (
                sum(error_times)
                / len(error_times)
                if error_times
                else 0
            ),
    }


# =============================================================================
# PRINT ERRORS
# =============================================================================

def print_errors(
    results,
    workers,
):

    errors = [
        result
        for result in results
        if not result["success"]
    ]

    if not errors:

        log.log(
            f"[ERROR DETAILS {workers}] "
            f"Ошибок нет."
        )

        return

    log.log("")
    log.log("=" * 100)

    log.log(
        f"ERROR DETAILS — "
        f"{workers} PROCESS(ES)"
    )

    log.log("=" * 100)

    log.log(
        f"Всего ошибок: "
        f"{len(errors)}"
    )

    log.log(
        f"Показываем первые "
        f"{min(SHOW_ERROR_DETAILS, len(errors))}"
    )

    log.log("-" * 100)

    for number, error in enumerate(
        errors[
            :SHOW_ERROR_DETAILS
        ],
        start=1,
    ):

        log.log(
            f"[ERROR #{number}]"
        )

        log.log(
            f"INDEX: "
            f"{error.get('index')}"
        )

        log.log(
            f"ROW: "
            f"{error.get('row_number')}"
        )

        log.log(
            f"URL: "
            f"{error.get('url')}"
        )

        log.log(
            f"TIME: "
            f"{error.get('elapsed', 0):.3f}s"
        )

        log.log(
            f"ERROR: "
            f"{error.get('error')}"
        )

        log.log(
            "TRACEBACK:"
        )

        log.log(
            error.get(
                "traceback",
                "",
            )
        )

        log.log("-" * 100)


# =============================================================================
# TEST ONE WORKER COUNT
# =============================================================================

def run_test(
    items,
    workers,
    learning_history,
):

    log.log("")
    log.log("=" * 100)

    log.log(
        f"TEST CLASSIFIER: "
        f"{workers} PROCESS(ES)"
    )

    log.log("=" * 100)

    chunks = split_items(
        items,
        workers,
    )

    for worker_id, chunk in enumerate(
        chunks,
        start=1,
    ):

        log.log(
            f"[PLAN] Process "
            f"{worker_id}: "
            f"{len(chunk)} cards"
        )

    started = time.perf_counter()

    all_results = []

    # -------------------------------------------------------------------------
    # IMPORTANT:
    #
    # Реальные процессы.
    # Каждый процесс получает собственный DecisionEngine.
    # -------------------------------------------------------------------------

    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=init_worker,
        initargs=(
            learning_history,
        ),
    ) as executor:

        futures = []

        for worker_id, chunk in enumerate(
            chunks,
            start=1,
        ):

            if not chunk:

                continue

            future = executor.submit(
                classify_batch,
                chunk,
            )

            futures.append(
                future
            )

        completed_chunks = 0

        for future in as_completed(
            futures
        ):

            try:

                batch_results = (
                    future.result()
                )

                all_results.extend(
                    batch_results
                )

                completed_chunks += 1

                if SHOW_PROGRESS:

                    elapsed = (
                        time.perf_counter()
                        - started
                    )

                    log.log(
                        f"[PROGRESS] "
                        f"Процессов завершено: "
                        f"{completed_chunks}/"
                        f"{len(futures)} | "
                        f"карточек готово: "
                        f"{len(all_results)} | "
                        f"{elapsed:.2f}s"
                    )

            except Exception:

                completed_chunks += 1

                log.log("")
                log.log(
                    "[TEST] ✗ PROCESS CRASHED"
                )

                log.log(
                    traceback.format_exc()
                )

    elapsed = (
        time.perf_counter()
        - started
    )

    # -------------------------------------------------------------------------
    # Сортировка для стабильного сравнения.
    # -------------------------------------------------------------------------

    all_results.sort(
        key=lambda x: x["index"]
    )

    stats = calculate_stats(
        all_results,
        elapsed,
    )

    # -------------------------------------------------------------------------
    # Печатаем реальные ошибки.
    # -------------------------------------------------------------------------

    print_errors(
        all_results,
        workers,
    )

    # -------------------------------------------------------------------------
    # SUMMARY
    # -------------------------------------------------------------------------

    log.log("")
    log.log(
        f"[TEST {workers}] "
        f"TIME: "
        f"{stats['elapsed']:.2f}s"
    )

    log.log(
        f"[TEST {workers}] "
        f"AVG SUCCESS CARD: "
        f"{stats['avg_card_time']:.3f}s"
    )

    log.log(
        f"[TEST {workers}] "
        f"SPEED: "
        f"{stats['speed']:.3f} card/s"
    )

    log.log(
        f"[TEST {workers}] "
        f"PER HOUR: "
        f"{stats['per_hour']:,.0f}"
    )

    log.log(
        f"[TEST {workers}] "
        f"PER 24H: "
        f"{stats['per_day']:,.0f}"
    )

    log.log(
        f"[TEST {workers}] "
        f"OK: "
        f"{stats['successful']}"
    )

    log.log(
        f"[TEST {workers}] "
        f"ERROR: "
        f"{stats['errors']}"
    )

    log.log(
        f"[TEST {workers}] "
        f"ERROR AVG TIME: "
        f"{stats['error_avg_time']:.3f}s"
    )

    log.log(
        f"[TEST {workers}] "
        f"p50={stats['p50']:.3f}s | "
        f"p90={stats['p90']:.3f}s | "
        f"p99={stats['p99']:.3f}s | "
        f"max={stats['max']:.3f}s"
    )

    return {

        "workers":
            workers,

        "stats":
            stats,

        "results":
            all_results,
    }


# =============================================================================
# MAIN
# =============================================================================

def main():

    import multiprocessing

    multiprocessing.freeze_support()

    log.log("")
    log.log("=" * 100)
    log.log(
        "CLASSIFIER PARALLEL TEST (PROCESSES)"
    )
    log.log("=" * 100)

    log.log(
        f"Python: {sys.version}"
    )

    log.log(
        f"CPU: {os.cpu_count()}"
    )

    log.log(
        f"Input: {INPUT_FILE}"
    )

    log.log(
        f"Worker tests: {WORKER_COUNTS}"
    )

    log.log("=" * 100)

    # =========================================================================
    # LOAD PHASE 1
    # =========================================================================

    phase1 = get_phase1_results()

    if not phase1:

        raise RuntimeError(
            "Нет parsed-карточек для теста."
        )

    if LIMIT is not None:

        phase1 = phase1[
            :LIMIT
        ]

    items = []

    for index, original in enumerate(
        phase1,
        start=1,
    ):

        item = dict(
            original
        )

        item["_test_index"] = (
            index
        )

        items.append(
            item
        )

    log.log("")
    log.log(
        f"[DATA] Карточек для теста: "
        f"{len(items)}"
    )

    # =========================================================================
    # LEARNING HISTORY
    # =========================================================================

    log.log(
        "[INIT] Загружаем learning history..."
    )

    learning_history = (
        load_learning_history(
            INPUT_FILE
        )
    )

    log.log(
        "[INIT] ✓ Learning history загружена"
    )

    # =========================================================================
    # RUN TESTS
    # =========================================================================

    all_tests = []

    baseline_results = None

    for workers in WORKER_COUNTS:

        test = run_test(
            items=items,
            workers=workers,
            learning_history=learning_history,
        )

        all_tests.append(
            test
        )

        # ---------------------------------------------------------------------
        # 1 process = baseline
        # ---------------------------------------------------------------------

        if workers == 1:

            baseline_results = (
                test["results"]
            )

        # ---------------------------------------------------------------------
        # Compare all multiprocessing results
        # against 1-process result.
        # ---------------------------------------------------------------------

        if (
            baseline_results is not None
            and workers != 1
        ):

            differences = (
                compare_results(
                    baseline_results,
                    test["results"],
                )
            )

            log.log("")

            if not differences:

                log.log(
                    f"[COMPARE {workers}] "
                    f"✓ Результаты совпадают "
                    f"с 1-process baseline"
                )

            else:

                log.log(
                    f"[COMPARE {workers}] "
                    f"!!! РАЗЛИЧИЯ: "
                    f"{len(differences)}"
                )

                for difference in (
                    differences[:20]
                ):

                    log.log(
                        f"    #"
                        f"{difference.get('index')} "
                        f"{difference.get('field', '')}: "
                        f"{difference.get('baseline')} "
                        f"-> "
                        f"{difference.get('parallel')}"
                    )

                if len(differences) > 20:

                    log.log(
                        f"    ... ещё "
                        f"{len(differences) - 20}"
                    )

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================

    log.log("")
    log.log("=" * 100)

    log.log(
        "ИТОГ PARALLEL CLASSIFIER TEST (PROCESSES)"
    )

    log.log("=" * 100)

    log.log(
        f"{'WORKERS':>8} | "
        f"{'TIME':>10} | "
        f"{'AVG/CARD':>10} | "
        f"{'CARD/S':>10} | "
        f"{'PER HOUR':>12} | "
        f"{'PER DAY':>12} | "
        f"{'OK':>8} | "
        f"{'ERRORS':>8}"
    )

    log.log(
        "-" * 100
    )

    baseline_time = None

    for test in all_tests:

        workers = test[
            "workers"
        ]

        stats = test[
            "stats"
        ]

        if workers == 1:

            baseline_time = (
                stats["elapsed"]
            )

        speedup = (
            baseline_time
            / stats["elapsed"]
            if baseline_time
            else 1
        )

        log.log(
            f"{workers:>8} | "
            f"{stats['elapsed']:>10.2f} | "
            f"{stats['avg_card_time']:>10.3f} | "
            f"{stats['speed']:>10.3f} | "
            f"{stats['per_hour']:>12,.0f} | "
            f"{stats['per_day']:>12,.0f} | "
            f"{stats['successful']:>8} | "
            f"{stats['errors']:>8}"
        )

        if workers > 1:

            log.log(
                f"         SPEEDUP: "
                f"{speedup:.2f}x"
            )

    # =========================================================================
    # SAVE JSON
    # =========================================================================

    output = []

    for test in all_tests:

        output.append({

            "workers":
                test["workers"],

            "stats":
                test["stats"],

            "results":
                test["results"],
        })

    with Path(
        RESULT_JSON
    ).open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    log.log("")
    log.log(
        f"[SAVE] ✓ Результаты: "
        f"{RESULT_JSON}"
    )

    log.log(
        f"[SAVE] ✓ Лог: "
        f"{LOG_FILE}"
    )

    log.log("")
    log.log("=" * 100)
    log.log("FINISHED")
    log.log("=" * 100)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    main()
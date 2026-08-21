import copy
import json
import statistics
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from engines.decision_engine import DecisionEngine
from modules.product_card import ProductCard

# =============================================================================
# CONFIG
# =============================================================================

CARDS_FILE = Path("storage/runtime_cards.json")

# Сколько карточек использовать для теста.
# None = все карточки.
TEST_LIMIT = 468

# Какие количества workers тестировать.
WORKERS_LIST = [1, 2, 3, 4]

# Сколько раз повторять каждый workers-тест.
# 1 достаточно для первого измерения.
REPEATS = 1

# CACHE:
#   работает как реальный DecisionEngine
#
# FULL:
#   CardClassifier отключается, чтобы увидеть стоимость
#   остальной цепочки классификации.
MODE = "FULL"

# Не сохраняем результаты классификации.
REMEMBER = False

# JSON отчёт
REPORT_FILE = Path("parallel_classifier_profile.json")


# =============================================================================
# UTILS
# =============================================================================

def now():
    return time.perf_counter()


def percentile(values, p):
    if not values:
        return 0.0

    values = sorted(values)

    if len(values) == 1:
        return float(values[0])

    k = (len(values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)

    if f == c:
        return float(values[f])

    return values[f] + (values[c] - values[f]) * (k - f)


def stats(values):
    if not values:
        return {
            "count": 0,
            "total": 0.0,
            "avg": 0.0,
            "p50": 0.0,
            "p90": 0.0,
            "p99": 0.0,
            "max": 0.0,
        }

    return {
        "count": len(values),
        "total": sum(values),
        "avg": statistics.mean(values),
        "p50": percentile(values, 50),
        "p90": percentile(values, 90),
        "p99": percentile(values, 99),
        "max": max(values),
    }


# =============================================================================
# THREAD LOCAL
# =============================================================================

_thread_local = threading.local()


# =============================================================================
# PROFILER
# =============================================================================

class StageProfiler:

    STAGES = [
        "special_products",
        "product_engine",
        "dropdown_resolve",
        "dropdown_resolve_code",
        "card_classifier",
        "trace_classifier",
        "history_classifier",
        "learning_classifier",
        "name_builder",
        "repository_remember",
        "total_decide",
    ]

    def __init__(self):
        self.lock = threading.Lock()

        self.times = {
            stage: []
            for stage in self.STAGES
        }

        self.calls = {
            stage: 0
            for stage in self.STAGES
        }

        self.errors = []

        self.branch_counts = {
            "SPECIAL_PRODUCT": 0,
            "CARD_CACHE": 0,
            "FULL_CLASSIFICATION": 0,
            "OTHER": 0,
        }

    def record(self, stage, elapsed):
        with self.lock:
            self.calls[stage] += 1
            self.times[stage].append(elapsed)

    def error(self, message):
        with self.lock:
            self.errors.append(message)

    def branch(self, name):
        with self.lock:
            if name not in self.branch_counts:
                name = "OTHER"

            self.branch_counts[name] += 1

    def report(self):
        result = {}

        for stage in self.STAGES:
            result[stage] = {
                "calls": self.calls[stage],
                **stats(self.times[stage]),
            }

        return result


# =============================================================================
# PROFILED DECISION ENGINE
# =============================================================================

class ProfiledDecisionEngine:

    """
    Обёртка над реальным DecisionEngine.

    Сам DecisionEngine НЕ изменяем.

    Мы просто измеряем время отдельных внутренних компонентов.
    """

    def __init__(self, learning_history, profiler, mode="CACHE"):
        self.real = DecisionEngine(learning_history)

        self.profiler = profiler
        self.mode = mode

        # ---------------------------------------------------------------------
        # Сохраняем оригинальные объекты
        # ---------------------------------------------------------------------

        self._special_products = self.real.special_products
        self._product_engine = self.real.product_engine
        self._dropdown = self.real.dropdown
        self._card_classifier = self.real.card_classifier
        self._trace_classifier = self.real.trace_classifier
        self._history_classifier = self.real.history_classifier
        self._learning_classifier = self.real.learning_classifier

        # ---------------------------------------------------------------------
        # В FULL режиме отключаем CardClassifier.
        #
        # Это позволяет увидеть стоимость дальнейшей цепочки.
        # ---------------------------------------------------------------------

        if self.mode == "FULL":

            class DisabledCardClassifier:

                def apply(self, card, result):
                    return None

            self.real.card_classifier = DisabledCardClassifier()

    # =========================================================================
    # DECIDE
    # =========================================================================

    def decide(self, card):

        total_start = now()

        try:

            # ================================================================
            # SPECIAL PRODUCT
            # ================================================================

            start = now()

            special = self.real.special_products.resolve(card)

            self.profiler.record(
                "special_products",
                now() - start,
            )

            if special:

                self.profiler.branch(
                    "SPECIAL_PRODUCT"
                )

                start = now()

                result = self.real.product_engine.classify(card)

                self.profiler.record(
                    "product_engine",
                    now() - start,
                )

                result.product = special["product"]
                result.dropdown = special["dropdown"]
                result.display_name = special["display_name"]
                result.code = special["code"]
                result.source = special["source"]
                result.confidence = special["confidence"]
                result.review = special["review"]

                result.quantity = getattr(
                    card,
                    "quantity",
                    "",
                )

                result.material = getattr(
                    card,
                    "material",
                    "",
                )

                result.trace.add(
                    "SPECIAL_PRODUCT",
                    f"Специальное правило: {special['source']}"
                )

                return result

            # ================================================================
            # PRODUCT ENGINE
            # ================================================================

            start = now()

            result = self.real.product_engine.classify(card)

            self.profiler.record(
                "product_engine",
                now() - start,
            )

            result.quantity = getattr(
                card,
                "quantity",
                "",
            )

            result.material = getattr(
                card,
                "material",
                "",
            )

            # ================================================================
            # DROPDOWN
            # ================================================================

            start = now()

            dropdown_exists = self.real.dropdown.resolve(
                result.product
            )

            self.profiler.record(
                "dropdown_resolve",
                now() - start,
            )

            if dropdown_exists:

                start = now()

                self.real.dropdown.resolve_code(
                    result,
                    card,
                )

                self.profiler.record(
                    "dropdown_resolve_code",
                    now() - start,
                )

            # ================================================================
            # CARD CLASSIFIER
            # ================================================================

            start = now()

            result_from_card = self.real.card_classifier.apply(
                card,
                result,
            )

            self.profiler.record(
                "card_classifier",
                now() - start,
            )

            if result_from_card:

                self.profiler.branch(
                    "CARD_CACHE"
                )

                return result_from_card

            # ================================================================
            # FULL CLASSIFICATION
            # ================================================================

            self.profiler.branch(
                "FULL_CLASSIFICATION"
            )

            # ================================================================
            # TRACE
            # ================================================================

            start = now()

            result = self.real.trace_classifier.apply(
                card,
                result,
            )

            self.profiler.record(
                "trace_classifier",
                now() - start,
            )

            # ================================================================
            # HISTORY
            # ================================================================

            start = now()

            result = self.real.history_classifier.apply(
                result,
                card,
            )

            self.profiler.record(
                "history_classifier",
                now() - start,
            )

            # ================================================================
            # LEARNING
            # ================================================================

            start = now()

            result = self.real.learning_classifier.apply(
                result,
            )

            self.profiler.record(
                "learning_classifier",
                now() - start,
            )

            # ================================================================
            # NAME BUILDER
            # ================================================================

            start = now()

            from resolver.excel_name_builder import ExcelNameBuilder

            builder = ExcelNameBuilder()

            result.dropdown = builder.build(
                card,
                result.product,
            )

            result.display_name = result.dropdown

            self.profiler.record(
                "name_builder",
                now() - start,
            )

            # ================================================================
            # REMEMBER
            # ================================================================

            if REMEMBER:

                start = now()

                self.real.knowledge.card_repository.remember(
                    card,
                    result,
                )

                self.profiler.record(
                    "repository_remember",
                    now() - start,
                )

            return result

        except Exception as exc:

            self.profiler.error(
                f"{type(exc).__name__}: {exc}"
            )

            raise

        finally:

            self.profiler.record(
                "total_decide",
                now() - total_start,
            )


# =============================================================================
# CARD LOADING
# =============================================================================

def load_cards():

    print()
    print("=" * 100)
    print("LOADING CARDS")
    print("=" * 100)

    if not CARDS_FILE.exists():

        raise FileNotFoundError(
            f"Не найден файл: {CARDS_FILE}"
        )

    with open(
        CARDS_FILE,
        "r",
        encoding="utf-8",
    ) as f:

        data = json.load(f)

    if not isinstance(data, dict):

        raise RuntimeError(
            "runtime_cards.json должен содержать JSON object"
        )

    cards = []

    for url, item in data.items():

        if not isinstance(item, dict):
            continue

        item = copy.deepcopy(item)

        item.setdefault(
            "url",
            url,
        )

        cards.append(item)

    if TEST_LIMIT:
        cards = cards[:TEST_LIMIT]

    print(
        f"[CARDS] Загружено: {len(cards)}"
    )

    return cards


# =============================================================================
# BUILD CARD
# =============================================================================

def build_card(item):

    """
    Создаём ProductCard тем же способом,
    которым пользуется рабочий processor.
    """

    card = ProductCard()
    card.url = item.get(
        "url",
        "",
    )

    card.title = item.get(
        "title",
        "",
    )

    card.description = item.get(
        "description",
        "",
    )

    card.cleaned_text = item.get(
        "cleaned_text",
        "",
    )

    card.slug = item.get(
        "slug",
        "",
    )

    card.material = item.get(
        "material",
        "",
    )

    card.quantity = item.get(
        "quantity",
        "",
    )

    card.brand = item.get(
        "brand",
        "",
    )

    card.country = item.get(
        "country",
        "",
    )

    card.specs = item.get(
        "specs",
        {},
    )

    card.sections = item.get(
        "sections",
        {},
    )

    card.features = item.get(
        "features",
        {},
    )

    card.images = item.get(
        "images",
        [],
    )

    return card


# =============================================================================
# WORKER
# =============================================================================

def worker(
    item,
    engine,
    index,
):

    card = build_card(item)

    try:

        result = engine.decide(
            card,
        )

        return {
            "index": index,
            "success": True,
            "result": result,
        }

    except Exception as exc:

        return {
            "index": index,
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }


# =============================================================================
# SINGLE TEST
# =============================================================================

def run_test(
    cards,
    workers,
    learning_history,
    mode,
):

    print()
    print("=" * 100)
    print(
        f"TEST: WORKERS={workers} | MODE={mode}"
    )
    print("=" * 100)

    profiler = StageProfiler()

    # -------------------------------------------------------------------------
    # ВАЖНО:
    #
    # Для каждого worker создаём собственный DecisionEngine.
    #
    # DecisionEngine содержит repository / learning / engines.
    # Не заставляем несколько потоков одновременно работать с одним
    # мутируемым экземпляром.
    # -------------------------------------------------------------------------

    engines = []

    for worker_id in range(workers):

        engine = ProfiledDecisionEngine(
            learning_history,
            profiler,
            mode=mode,
        )

        engines.append(
            engine
        )

    start = now()

    errors = []

    completed = 0

    # -------------------------------------------------------------------------
    # ThreadPool
    # -------------------------------------------------------------------------

    with ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="ClassifierWorker",
    ) as executor:

        futures = []

        for index, item in enumerate(
            cards,
            start=1,
        ):

            engine = engines[
                (index - 1) % workers
            ]

            futures.append(
                executor.submit(
                    worker,
                    item,
                    engine,
                    index,
                )
            )

        for future in as_completed(
            futures
        ):

            result = future.result()

            completed += 1

            if not result["success"]:

                errors.append(
                    result
                )

            if (
                completed % 25 == 0
                or completed == len(cards)
            ):

                elapsed = now() - start

                speed = (
                    completed / elapsed
                    if elapsed > 0
                    else 0
                )

                print(
                    f"[{completed:4d}/{len(cards)}] "
                    f"{elapsed:8.2f}s | "
                    f"{speed:.3f} card/s"
                )

    elapsed = now() - start

    card_per_sec = (
        len(cards) / elapsed
        if elapsed > 0
        else 0
    )

    per_hour = card_per_sec * 3600
    per_day = card_per_sec * 86400

    stage_report = profiler.report()

    # -------------------------------------------------------------------------
    # PRINT
    # -------------------------------------------------------------------------

    print()
    print("=" * 100)
    print(
        f"RESULT: WORKERS={workers} | MODE={mode}"
    )
    print("=" * 100)

    print(
        f"Cards:       {len(cards)}"
    )

    print(
        f"Time:        {elapsed:.2f} sec"
    )

    print(
        f"Avg/card:    {elapsed / len(cards):.3f} sec"
    )

    print(
        f"Card/sec:    {card_per_sec:.3f}"
    )

    print(
        f"Per hour:    {per_hour:,.0f}"
    )

    print(
        f"Per 24h:     {per_day:,.0f}"
    )

    print(
        f"Errors:      {len(errors)}"
    )

    # -------------------------------------------------------------------------
    # BRANCHES
    # -------------------------------------------------------------------------

    print()
    print("-" * 100)
    print("BRANCH DISTRIBUTION")
    print("-" * 100)

    for name, count in (
        profiler.branch_counts.items()
    ):

        print(
            f"{name:25s}: {count:6d}"
        )

    # -------------------------------------------------------------------------
    # STAGES
    # -------------------------------------------------------------------------

    print()
    print("-" * 100)
    print("STAGE PROFILE")
    print("-" * 100)

    print(
        f"{'STAGE':28s}"
        f"{'CALLS':>8s}"
        f"{'TOTAL':>12s}"
        f"{'AVG':>12s}"
        f"{'P50':>12s}"
        f"{'P90':>12s}"
        f"{'P99':>12s}"
        f"{'MAX':>12s}"
    )

    print("-" * 100)

    for stage in (
        StageProfiler.STAGES
    ):

        data = stage_report[stage]

        print(
            f"{stage:28s}"
            f"{data['calls']:8d}"
            f"{data['total']:12.2f}"
            f"{data['avg']:12.4f}"
            f"{data['p50']:12.4f}"
            f"{data['p90']:12.4f}"
            f"{data['p99']:12.4f}"
            f"{data['max']:12.4f}"
        )

    # -------------------------------------------------------------------------
    # ERRORS
    # -------------------------------------------------------------------------

    if errors:

        print()
        print("-" * 100)
        print("ERRORS")
        print("-" * 100)

        for error in errors[:10]:

            print(
                f"[{error['index']}] "
                f"{error['error']}"
            )

    return {
        "workers": workers,
        "mode": mode,
        "cards": len(cards),
        "time": elapsed,
        "avg_card": elapsed / len(cards),
        "card_per_sec": card_per_sec,
        "per_hour": per_hour,
        "per_day": per_day,
        "errors": len(errors),
        "branches": profiler.branch_counts.copy(),
        "stages": stage_report,
    }


# =============================================================================
# MAIN
# =============================================================================

def main():

    print()
    print("=" * 100)
    print("PARALLEL CLASSIFIER PROFILE")
    print("=" * 100)

    print(
        f"[CONFIG] Cards:   {CARDS_FILE}"
    )

    print(
        f"[CONFIG] Limit:   {TEST_LIMIT}"
    )

    print(
        f"[CONFIG] Workers: {WORKERS_LIST}"
    )

    print(
        f"[CONFIG] Mode:    {MODE}"
    )

    print(
        f"[CONFIG] Remember:{REMEMBER}"
    )

    # -------------------------------------------------------------------------
    # LOAD
    # -------------------------------------------------------------------------

    cards = load_cards()

    if not cards:

        raise RuntimeError(
            "Нет карточек для тестирования"
        )

    # -------------------------------------------------------------------------
    # learning history
    #
    # DecisionEngine требует learning_history.
    # Берём пустой список, если полноценная история не нужна для теста.
    # -------------------------------------------------------------------------

    learning_history = []

    # -------------------------------------------------------------------------
    # RUN
    # -------------------------------------------------------------------------

    all_results = []

    for workers in WORKERS_LIST:

        for repeat in range(
            REPEATS
        ):

            if REPEATS > 1:

                print()
                print(
                    f"REPEAT {repeat + 1}/{REPEATS}"
                )

            try:

                result = run_test(
                    cards,
                    workers,
                    learning_history,
                    MODE,
                )

                all_results.append(
                    result
                )

            except Exception:

                print()
                print(
                    "!!! TEST ERROR !!!"
                )

                traceback.print_exc()

    # =========================================================================
    # SUMMARY
    # =========================================================================

    print()
    print()
    print("=" * 100)
    print("FINAL SUMMARY")
    print("=" * 100)

    print(
        f"{'WORKERS':>8s}"
        f"{'TIME':>14s}"
        f"{'AVG/CARD':>14s}"
        f"{'CARD/S':>12s}"
        f"{'PER HOUR':>14s}"
        f"{'PER DAY':>14s}"
        f"{'ERRORS':>10s}"
    )

    print("-" * 100)

    baseline = None

    for result in all_results:

        if result["workers"] == 1:

            if baseline is None:

                baseline = result["card_per_sec"]

        speedup = (
            result["card_per_sec"] / baseline
            if baseline
            else 0
        )

        print(
            f"{result['workers']:8d}"
            f"{result['time']:14.2f}"
            f"{result['avg_card']:14.3f}"
            f"{result['card_per_sec']:12.3f}"
            f"{result['per_hour']:14,.0f}"
            f"{result['per_day']:14,.0f}"
            f"{result['errors']:10d}"
        )

        if baseline:

            print(
                f"         SPEEDUP: {speedup:.2f}x"
            )

    # =========================================================================
    # BOTTLENECK
    # =========================================================================

    if all_results:

        best = max(
            all_results,
            key=lambda x: x["card_per_sec"],
        )

        print()
        print("=" * 100)
        print("BEST RESULT")
        print("=" * 100)

        print(
            f"Workers:     {best['workers']}"
        )

        print(
            f"Time:        {best['time']:.2f}s"
        )

        print(
            f"Speed:       {best['card_per_sec']:.3f} card/s"
        )

        print(
            f"Per hour:    {best['per_hour']:,.0f}"
        )

        print(
            f"Per 24h:     {best['per_day']:,.0f}"
        )

        print()
        print("-" * 100)
        print("BRANCHES")
        print("-" * 100)

        for name, count in (
            best["branches"].items()
        ):

            print(
                f"{name:25s}: {count}"
            )

        # ---------------------------------------------------------------------
        # BOTTLENECK BY TOTAL CPU TIME
        # ---------------------------------------------------------------------

        print()
        print("-" * 100)
        print("BOTTLENECK BY STAGE")
        print("-" * 100)

        stage_items = []

        for stage, data in (
            best["stages"].items()
        ):

            if (
                stage == "total_decide"
            ):
                continue

            stage_items.append(
                (
                    stage,
                    data["total"],
                )
            )

        stage_items.sort(
            key=lambda x: x[1],
            reverse=True,
        )

        total_stage_time = sum(
            value
            for _, value
            in stage_items
        )

        for stage, total in stage_items:

            percent = (
                total / total_stage_time * 100
                if total_stage_time
                else 0
            )

            print(
                f"{stage:28s}"
                f"{total:12.2f}s"
                f"{percent:8.1f}%"
            )

    # =========================================================================
    # SAVE JSON
    # =========================================================================

    report = {
        "config": {
            "cards_file": str(
                CARDS_FILE
            ),
            "test_limit": TEST_LIMIT,
            "workers": WORKERS_LIST,
            "repeats": REPEATS,
            "mode": MODE,
            "remember": REMEMBER,
        },
        "results": all_results,
    }

    with open(
        REPORT_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=4,
        )

    print()
    print(f"[SAVE] ✓ {REPORT_FILE}")
    print()
    print("=" * 100)
    print("FINISHED")
    print("=" * 100)

# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()
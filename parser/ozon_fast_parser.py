import json
import queue
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


# =============================================================================
# CONFIG
# =============================================================================
CDP_URL = "http://127.0.0.1:9222"
WORKERS = 3
NAVIGATION_TIMEOUT = 30_000
RESULT_FILE = Path("ozon_fast_results.json")
LOG_FILE = Path("ozon_fast_results.log")
# =============================================================================
# TEST URLS
# =============================================================================
TEST_URLS = [
    "https://www.ozon.ru/product/5293991761/",
    "https://www.ozon.ru/product/4852033249/",
    "https://www.ozon.ru/product/5294134418/",
    "https://www.ozon.ru/product/4543849841/",
    "https://www.ozon.ru/product/4661565890/",
    "https://www.ozon.ru/product/5314610714/",
    "https://www.ozon.ru/product/5303597145/",
    "https://www.ozon.ru/product/3396713352/",
    "https://www.ozon.ru/product/5237080856/",
    "https://www.ozon.ru/product/4951373458/",
    "https://www.ozon.ru/product/5149698916/",
]
# =============================================================================
# PARSER
# =============================================================================
try:

    from parser.ozon_html_parser import parse_ozon_html

    PARSER_AVAILABLE = True

except Exception as exc:

    parse_ozon_html = None
    PARSER_AVAILABLE = False

    print(
        "[INIT] ✗ Не удалось импортировать "
        "parse_ozon_html()"
    )
    print(
        "[INIT] ERROR:",
        repr(exc),
    )
# =============================================================================
# LOGGER
# =============================================================================
class Logger:

    def __init__(self, filename: Path):

        self.filename = filename
        self.lock = threading.Lock()
        self.filename.write_text(
            "",
            encoding="utf-8",
        )

    def log(self, message: str):

        with self.lock:

            print(message, flush=True)

            with self.filename.open(
                "a",
                encoding="utf-8",
            ) as file:

                file.write(message + "\n")
# =============================================================================
# WORK ITEM
# =============================================================================
class WorkItem:

    def __init__(self, index: int, url: str):

        self.index = index
        self.url = url
# =============================================================================
# FAST PARSER
# =============================================================================
class OzonFastParser:

    def __init__(
        self,
        workers: int = 2,
        logger: Logger | None = None,
    ):
        self.workers = workers
        self.logger = logger or Logger(LOG_FILE)
        self.results = []
        self.results_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.work_queue = queue.Queue()
        self.start_time = None
    # =========================================================================
    # WORKER
    # =========================================================================

    def worker(self, worker_id: int):

        """
        Нельзя создать Playwright в main thread
        и передавать page/context в другой thread.
        """

        self.logger.log("")
        self.logger.log("=" * 90)
        self.logger.log(f"[WORKER {worker_id}] START")
        # =====================================================================
        # СОЗДАЁМ PLAYWRIGHT ВНУТРИ ЭТОГО THREAD
        # =====================================================================

        try:

            with sync_playwright() as p:

                self.logger.log(
                    f"[WORKER {worker_id}] "
                    f"Подключаемся к CDP..."
                )

                browser = (
                    p.chromium.connect_over_cdp(
                        CDP_URL
                    )
                )

                self.logger.log(
                    f"[WORKER {worker_id}] "
                    f"✓ CDP подключён"
                )

                contexts = browser.contexts

                self.logger.log(
                    f"[WORKER {worker_id}] "
                    f"Contexts: {len(contexts)}"
                )

                if not contexts:

                    raise RuntimeError(
                        "Browser contexts отсутствуют"
                    )

                context = contexts[0]

                self.logger.log(
                    f"[WORKER {worker_id}] "
                    f"Pages до создания: "
                    f"{len(context.pages)}"
                )

                # =================================================================
                # СОЗДАЁМ СОБСТВЕННУЮ СТРАНИЦУ
                # =================================================================

                page = context.new_page()

                page.set_default_timeout(
                    NAVIGATION_TIMEOUT
                )

                page.set_default_navigation_timeout(
                    NAVIGATION_TIMEOUT
                )

                self.logger.log(
                    f"[WORKER {worker_id}] "
                    f"✓ Собственная page создана"
                )

                # =================================================================
                # ОСНОВНОЙ ЦИКЛ
                # =================================================================

                while not self.stop_event.is_set():

                    try:

                        item = (
                            self.work_queue.get_nowait()
                        )

                    except queue.Empty:

                        break

                    try:

                        result = self.process_one(
                            worker_id,
                            page,
                            item,
                        )

                        with self.results_lock:

                            self.results.append(
                                result
                            )

                    except Exception as exc:

                        self.logger.log(
                            f"[WORKER {worker_id}] "
                            f"[{item.index}] "
                            f"✗ FATAL:"
                        )

                        self.logger.log(
                            traceback.format_exc()
                        )

                        with self.results_lock:

                            self.results.append(
                                {
                                    "index": item.index,
                                    "url": item.url,
                                    "worker": worker_id,
                                    "success": False,
                                    "error": (
                                        f"Worker error: "
                                        f"{type(exc).__name__}: "
                                        f"{exc}"
                                    ),
                                }
                            )

                    finally:

                        self.work_queue.task_done()

                # =================================================================
                # CLOSE PAGE
                # =================================================================

                try:

                    page.close()

                except Exception:

                    pass

                self.logger.log(
                    f"[WORKER {worker_id}] "
                    f"Page закрыта"
                )

                try:

                    browser.close()

                except Exception:

                    pass

                self.logger.log(
                    f"[WORKER {worker_id}] "
                    f"CDP connection закрыто"
                )

        except Exception as exc:

            self.logger.log(
                f"[WORKER {worker_id}] "
                f"✗ НЕ УДАЛОСЬ ЗАПУСТИТЬ WORKER"
            )

            self.logger.log(
                traceback.format_exc()
            )

        self.logger.log(
            f"[WORKER {worker_id}] STOP"
        )

    # =========================================================================
    # PROCESS ONE
    # =========================================================================

    def process_one(
        self,
        worker_id: int,
        page,
        item: WorkItem,
    ) -> dict[str, Any]:

        index = item.index

        url = item.url

        overall_start = time.perf_counter()

        self.logger.log(
            ""
        )

        self.logger.log(
            "-" * 90
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] START"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] URL: {url}"
        )

        # =====================================================================
        # GOTO
        # =====================================================================

        goto_start = time.perf_counter()

        response = None

        try:

            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT,
            )

        except Exception as exc:

            total_time = (
                time.perf_counter()
                - overall_start
            )

            self.logger.log(
                f"[WORKER {worker_id}] "
                f"[{index}] "
                f"✗ GOTO ERROR: {repr(exc)}"
            )

            return {
                "index": index,
                "url": url,
                "worker": worker_id,
                "success": False,
                "status": None,
                "goto_time": (
                    time.perf_counter()
                    - goto_start
                ),
                "html_time": 0,
                "parser_time": 0,
                "total_time": total_time,
                "html_size": 0,
                "error": (
                    f"Goto error: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            }

        goto_time = (
            time.perf_counter()
            - goto_start
        )

        status = (
            response.status
            if response
            else None
        )

        final_url = page.url

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] STATUS: {status}"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] GOTO: "
            f"{goto_time:.3f}s"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] FINAL URL: "
            f"{final_url}"
        )

        # =====================================================================
        # 403
        # =====================================================================

        if status == 403:

            total_time = (
                time.perf_counter()
                - overall_start
            )

            self.logger.log(
                f"[WORKER {worker_id}] "
                f"[{index}] "
                f"!!! 403 !!!"
            )

            return {
                "index": index,
                "url": url,
                "worker": worker_id,
                "success": False,
                "status": 403,
                "final_url": final_url,
                "goto_time": goto_time,
                "html_time": 0,
                "parser_time": 0,
                "total_time": total_time,
                "html_size": 0,
                "title": "",
                "sku": "",
                "price": None,
                "images_count": 0,
                "captcha": True,
                "error": "HTTP 403",
            }

        # =====================================================================
        # HTML
        # =====================================================================

        html_start = time.perf_counter()

        try:

            html = page.content()

        except Exception as exc:

            total_time = (
                time.perf_counter()
                - overall_start
            )

            self.logger.log(
                f"[WORKER {worker_id}] "
                f"[{index}] "
                f"✗ CONTENT ERROR: "
                f"{repr(exc)}"
            )

            return {
                "index": index,
                "url": url,
                "worker": worker_id,
                "success": False,
                "status": status,
                "final_url": final_url,
                "goto_time": goto_time,
                "html_time": (
                    time.perf_counter()
                    - html_start
                ),
                "parser_time": 0,
                "total_time": total_time,
                "html_size": 0,
                "error": (
                    f"Content error: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                ),
            }

        html_time = (
            time.perf_counter()
            - html_start
        )

        html_size = len(html)

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] HTML: "
            f"{html_size:,} chars"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] HTML TIME: "
            f"{html_time:.3f}s"
        )

        # =====================================================================
        # ANTIBOT
        # =====================================================================

        lower_html = html.lower()

        captcha = (
            "captcha" in lower_html
            or "access denied" in lower_html
            or "проверка" in lower_html
        )

        if captcha:

            total_time = (
                time.perf_counter()
                - overall_start
            )

            self.logger.log(
                f"[WORKER {worker_id}] "
                f"[{index}] "
                f"!!! CAPTCHA / ANTIBOT !!!"
            )

            return {
                "index": index,
                "url": url,
                "worker": worker_id,
                "success": False,
                "status": status,
                "final_url": final_url,
                "goto_time": goto_time,
                "html_time": html_time,
                "parser_time": 0,
                "total_time": total_time,
                "html_size": html_size,
                "title": "",
                "sku": "",
                "price": None,
                "images_count": 0,
                "captcha": True,
                "error": (
                    "CAPTCHA / ANTIBOT detected"
                ),
            }

        # =====================================================================
        # PARSER
        # =====================================================================

        parser_start = time.perf_counter()
        parsed = {}
        parser_error = None

        if PARSER_AVAILABLE:

            try:

                parsed = parse_ozon_html(html)

            except Exception as exc:

                parser_error = (
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                self.logger.log(
                    f"[WORKER {worker_id}] "
                    f"[{index}] "
                    f"✗ PARSER ERROR: "
                    f"{repr(exc)}"
                )
        else:

            parser_error = ("parse_ozon_html unavailable")
        parser_time = (
            time.perf_counter()
            - parser_start
        )
        if not isinstance(
            parsed,
            dict,
        ):
            parsed = {}
        title = parsed.get("title", "")
        sku = parsed.get("sku", "")
        price = parsed.get("price")
        images = parsed.get("images", [])

        if not isinstance(
            images,
            list,
        ):
            images = []
        specs = parsed.get(
            "specs",
            {},
        )
        if not isinstance(
            specs,
            dict,
        ):
            specs = {}

        # =====================================================================
        # TOTAL
        # =====================================================================

        total_time = (
            time.perf_counter()
            - overall_start
        )

        success = (
            parser_error is None
            and bool(
                title
                or sku
                or price is not None
            )
        )

        # =====================================================================
        # LOG
        # =====================================================================

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] TITLE: "
            f"{str(title)[:100]}"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] SKU: {sku}"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] PRICE: {price}"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] IMAGES: "
            f"{len(images)}"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] PARSER: "
            f"{parser_time:.3f}s"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] TOTAL: "
            f"{total_time:.3f}s"
        )

        self.logger.log(
            f"[WORKER {worker_id}] "
            f"[{index}] "
            f"{'✓ SUCCESS' if success else '✗ FAILED'}"
        )

        return {
            "index": index,
            "url": url,
            "worker": worker_id,
            "success": success,
            "status": status,
            "final_url": final_url,
            "goto_time": goto_time,
            "html_time": html_time,
            "parser_time": parser_time,
            "total_time": total_time,
            "html_size": html_size,
            "title": title,
            "description": parsed.get(
                "description",
                "",
            ),
            "price": price,
            "currency": parsed.get(
                "currency"
            ),
            "sku": sku,
            "brand": parsed.get(
                "brand",
                "",
            ),
            "main_image": parsed.get(
                "main_image",
                "",
            ),
            "images": images,
            "images_count": len(images),
            "specs": specs,
            "specs_count": len(specs),
            "material": parsed.get(
                "material",
                "",
            ),
            "captcha": False,
            "error": parser_error,
        }

    # =========================================================================
    # RUN
    # =========================================================================

    def run(self, urls):

        self.start_time = time.perf_counter()
        # =====================================================================
        # QUEUE
        # =====================================================================

        for index, url in enumerate(
            urls,
            start=1,
        ):

            self.work_queue.put(
                WorkItem(
                    index=index,
                    url=url,
                )
            )

        self.logger.log(
            ""
        )

        self.logger.log(
            "=" * 90
        )

        self.logger.log(
            "RUN"
        )

        self.logger.log(
            f"URLs:    {len(urls)}"
        )

        self.logger.log(
            f"Workers: {self.workers}"
        )

        self.logger.log(
            "=" * 90
        )

        # =====================================================================
        # THREADS
        # =====================================================================

        threads = []

        for worker_id in range(
            1,
            self.workers + 1,
        ):

            thread = threading.Thread(
                target=self.worker,
                args=(worker_id,),
                name=f"OzonWorker-{worker_id}",
                daemon=True,
            )

            threads.append(
                thread
            )

            thread.start()

        # =====================================================================
        # WAIT
        # =====================================================================

        for thread in threads:

            thread.join()

        run_time = (
            time.perf_counter()
            - self.start_time
        )

        # =====================================================================
        # RESULTS
        # =====================================================================

        self.results.sort(
            key=lambda x: x.get(
                "index",
                0,
            )
        )

        self.print_summary(
            run_time
        )

        self.save_results(
            run_time
        )

    # =========================================================================
    # SUMMARY
    # =========================================================================

    def print_summary(
        self,
        run_time,
    ):

        total = len(
            self.results
        )

        successful = sum(
            1
            for r in self.results
            if r.get(
                "success"
            )
        )

        failed = total - successful

        captcha = sum(
            1
            for r in self.results
            if r.get(
                "captcha"
            )
        )

        status_200 = sum(
            1
            for r in self.results
            if r.get(
                "status"
            ) == 200
        )

        avg_time = (
            sum(
                r.get(
                    "total_time",
                    0,
                )
                for r in self.results
            )
            / total
            if total
            else 0
        )

        throughput = (
            total / run_time
            if run_time > 0
            else 0
        )

        per_hour = (throughput * 3600)
        per_day = (throughput * 86400)
        self.logger.log("")
        self.logger.log("")
        self.logger.log("=" * 90)
        self.logger.log("ИТОГ FAST TEST")
        self.logger.log("=" * 90)
        self.logger.log(
            f"Всего URL:                 {total}"
        )
        self.logger.log(
            f"HTTP 200:                  {status_200}"
        )
        self.logger.log(
            f"Успешно:                   {successful}"
        )
        self.logger.log(
            f"Ошибки:                    {failed}"
        )
        self.logger.log(
            f"CAPTCHA:                   {captcha}"
        )
        self.logger.log("")
        self.logger.log(
            f"Общее время:               "
            f"{run_time:.3f} сек"
        )
        self.logger.log(
            f"Среднее время URL:         "
            f"{avg_time:.3f} сек"
        )
        self.logger.log("")
        self.logger.log(
            f"Пропускная способность:    "
            f"{throughput:.3f} URL/сек"
        )
        self.logger.log(
            f"Расчётно в час:            "
            f"{per_hour:,.0f}"
        )
        self.logger.log(
            f"Расчётно за 24 часа:       "
            f"{per_day:,.0f}"
        )
        self.logger.log("")
        self.logger.log("РАСПРЕДЕЛЕНИЕ WORKERS:")

        for worker_id in range(
            1,
            self.workers + 1,
        ):

            worker_results = [
                r
                for r in self.results
                if r.get(
                    "worker"
                ) == worker_id
            ]

            if not worker_results:
                continue

            worker_time = sum(
                r.get(
                    "total_time",
                    0,
                )
                for r in worker_results
            )

            worker_avg = (
                worker_time
                / len(worker_results)
            )

            self.logger.log(
                f"    Worker {worker_id}: "
                f"{len(worker_results)} URL, "
                f"avg {worker_avg:.3f}s"
            )

        self.logger.log("=" * 90)
    # =========================================================================
    # SAVE
    # =========================================================================
    def save_results(self, run_time,):

        data = {
            "config": {
                "cdp_url": CDP_URL,
                "workers": self.workers,
            },
            "run_time": run_time,
            "results": self.results,
        }

        RESULT_FILE.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        self.logger.log(
            f"[SAVE] ✓ {RESULT_FILE}"
        )
# =============================================================================
# MAIN
# =============================================================================

def main():

    print()
    print("=" * 90)
    print("OZON FAST PARSER")
    print("=" * 90)
    print(f"CDP:     {CDP_URL}")
    print(f"Workers: {WORKERS}")
    print(f"URLs:    {len(TEST_URLS)}")
    print(
        f"Parser:  "
        f"{'OK' if PARSER_AVAILABLE else 'ERROR'}"
    )
    print("=" * 90)
    logger = Logger(LOG_FILE)
    parser = OzonFastParser(
        workers=WORKERS,
        logger=logger,
    )
    parser.run(TEST_URLS)
    print()
    print("=" * 90)
    print("FINISHED")
    print("=" * 90)
    print(f"Log:     {LOG_FILE}")
    print(f"Results: {RESULT_FILE}")
    print("=" * 90)


if __name__ == "__main__":

    main()
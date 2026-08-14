import inspect
import os
import subprocess
import time
import json
import requests

from playwright.sync_api import sync_playwright

from engines.image_description_engine import ImageDescriptionEngine
from parser.ozon_parser import OzonParser
from parser.wb_parser import WBParser
from models.card_builder import build_product_card
from processors.card_image_processor import CardImageProcessor
from services.image_description_service import ImageDescriptionService


class CDPProductParser:

    def __init__(self, cdp_url="http://127.0.0.1:9222"):

        self.cdp_url = cdp_url
        image_engine = ImageDescriptionEngine()
        image_service = ImageDescriptionService(image_engine)
        self.image_processor = CardImageProcessor(image_service)


    def kill_yandex_browser(self):

        subprocess.run(
            [
                "taskkill",
                "/F",
                "/IM",
                "browser.exe"
            ],
            capture_output=True
        )

        time.sleep(2)

    def is_cdp_running(self):

        try:

            requests.get(
                "http://127.0.0.1:9222/json/version",
                timeout=2
            )
            return True
        except:
            return False

    def start_yandex_browser(self):

        browser_path = (
            r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe"
        )
        if not os.path.exists(browser_path):
            raise Exception(
                "Не найден Яндекс.Браузер"
            )
        subprocess.Popen([
            browser_path,
            "--remote-debugging-port=9222"
        ])

        for _ in range(20):
            if self.is_cdp_running():
                return

            time.sleep(1)

        raise Exception(
            "Не удалось запустить CDP порт 9222"
        )


    def connect(self):

        if not self.is_cdp_running():
            self.start_yandex_browser()
        self.playwright = (sync_playwright().start())
        try:
            self.browser = (
                self.playwright.chromium.connect_over_cdp(self.cdp_url))
        except Exception:
            self.kill_yandex_browser()
            self.start_yandex_browser()
            self.browser = (
                self.playwright.chromium.connect_over_cdp(self.cdp_url))
        if self.browser.contexts:
            self.context = (self.browser.contexts[0])
        else:
            raise Exception("Не найден ни один контекст браузера")
        print("CDP подключен")

    def find_page_by_url(self, url):

        for page in self.context.pages:
            try:
                current_url = (page.url.lower())

                if url.lower() in current_url:
                    return page
            except:
                continue
        return None

    def open_url(self, url):

        page = self.context.new_page()
        network_requests = []

        # ==========================================================
        # NETWORK DIAGNOSTICS ONLY
        # ==========================================================

        def on_request(request):

            try:
                if request.resource_type not in (
                        "xhr",
                        "fetch",
                ):
                    return

                data = {
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                }
                network_requests.append(data)
                print(
                    "\n[API REQUEST]"
                    f"\n{request.method} {request.url}"
                )
            except Exception as e:

                print(
                    f"[API REQUEST ERROR] {e}"
                )

        def on_response(response):

            try:

                request = response.request

                if request.resource_type not in (
                        "xhr",
                        "fetch",
                ):
                    return
                # Служебный telemetry endpoint нам не интересен.
                if "logs-gateway" in response.url:
                    return

                print(
                    "\n[API RESPONSE]"
                    f"\n{response.status}"
                    f" {response.url}"
                )
            except Exception as e:

                print(
                    f"[API RESPONSE ERROR] {e}"
                )
        page.on(
            "request",
            on_request,
        )

        page.on(
            "response",
            on_response,
        )

        # ==========================================================
        # RESOURCE LIMITATION
        # ==========================================================

        def route_handler(route):

            try:

                resource_type = (
                    route.request.resource_type
                )

                if resource_type in (
                        "media",
                        "font",
                        "stylesheet",
                ):

                    route.abort()

                else:

                    route.continue_()

            except Exception as e:

                print(
                    f"[ROUTE ERROR] {e}"
                )

                try:
                    route.continue_()
                except Exception:
                    pass

        page.route(
            "**/*",
            route_handler,
        )

        # ==========================================================
        # OPEN PAGE
        # ==========================================================

        print(
            "\n========================================"
        )

        print(
            "[CDP] OPEN URL:"
        )

        print(url)

        print(
            "========================================"
        )

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

        except Exception as e:

            print(
                f"[CDP GOTO ERROR] {e}"
            )

            # Даже если domcontentloaded timeout,
            # страница может уже быть пригодна для парсинга.

        # ==========================================================
        # WAIT FOR PRODUCT
        # ==========================================================

        try:

            page.locator("h1").first.wait_for(
                state="visible",
                timeout=10000,
            )

            print(
                "[OZON PAGE] H1 FOUND"
            )

        except Exception as e:

            print(
                f"[OZON PAGE WARNING] "
                f"H1 NOT FOUND: {e}"
            )

        # ==========================================================
        # WAIT FOR JS / ASYNC PDP DATA
        # ==========================================================

        page.wait_for_timeout(1500)

        try:

            page.wait_for_load_state(
                "networkidle",
                timeout=7000,
            )

        except Exception:

            print(
                "[OZON PAGE] "
                "networkidle timeout - continuing"
            )

        # Небольшая пауза после networkidle:
        # Ozon может дорисовать async widgets.
        page.wait_for_timeout(1000)

        # ==========================================================
        # DIAGNOSTICS
        # ==========================================================

        try:

            body_length = page.locator(
                "body"
            ).inner_text()

            print(
                "[OZON PAGE] "
                f"FULL BODY TEXT: "
                f"{len(body_length)} chars"
            )

        except Exception as e:

            print(
                f"[OZON PAGE BODY ERROR] {e}"
            )

        # ==========================================================
        # SAVE NETWORK LIST ONLY
        # ==========================================================

        try:

            marketplace = (
                "ozon"
                if "ozon.ru" in url.lower()
                else
                "wildberries"
                if "wildberries.ru" in url.lower()
                else
                "unknown"
            )

            os.makedirs(
                "storage",
                exist_ok=True,
            )

            filename = (
                f"storage/"
                f"network_{marketplace}.json"
            )

            unique = {}

            for item in network_requests:
                key = (
                    item["method"],
                    item["url"],
                )

                unique[key] = item

            existing = []

            if os.path.exists(filename):

                try:

                    with open(
                            filename,
                            "r",
                            encoding="utf-8",
                    ) as f:

                        existing = json.load(f)

                except Exception as e:

                    print(
                        f"[NETWORK LOAD WARNING] {e}"
                    )

                    existing = []

            existing_keys = {
                (
                    item.get("method"),
                    item.get("url"),
                )
                for item in existing
            }

            new_items = []

            for item in unique.values():

                key = (
                    item["method"],
                    item["url"],
                )

                if key not in existing_keys:
                    new_items.append(item)

            if new_items:
                existing.extend(
                    new_items
                )

                with open(
                        filename,
                        "w",
                        encoding="utf-8",
                ) as f:
                    json.dump(
                        existing,
                        f,
                        ensure_ascii=False,
                        indent=2,
                    )

                print(
                    "[NETWORK SAVED]"
                    f" {filename}"
                )

                print(
                    "[NEW API REQUESTS]"
                    f" {len(new_items)}"
                )

        except Exception as e:

            print(
                f"[NETWORK SAVE ERROR] {e}"
            )

        return page

    def wait_page_ready(self, page):
        try:
            page.wait_for_load_state(
                "networkidle",
                timeout=7000
            )
        except:
            pass

    def parse_page_text(self, page):

        url = page.url.lower()

        if "wildberries.ru" in url:
            parser = WBParser()
            print(inspect.getfile(WBParser))
        else:
            parser = OzonParser()
            print(inspect.getfile(OzonParser))
        parsed = parser.parse_page(page)
        try:
            page.evaluate(
                """
                () => {
                    window.stop();
                }
                """
            )
        except Exception as e:

            print(f"[PAGE STOP WARNING] {e}")

        card = build_product_card(
            page.url,
            parsed,
            parsed["raw_text"],
        )
        print(
            "[CDP CARD]"
            f" TITLE={bool(card.title)}"
            f" DESCRIPTION={len(card.description or '')}"
            f" IMAGES={len(card.images)}"
        )
        return card

    def parse_url(self, url):
        page = self.find_page_by_url(url) or self.open_url(url)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        data = parse_ozon_page(page)
        return build_product_card(url, data, raw_text=data["description"])

    def disconnect(self):

        try:
            self.browser.close()
        except:
            pass
        try:
            self.playwright.stop()
        except:
            pass

    def get_marketplace_pages(self):

        result = []

        for page in self.context.pages:

            try:

                url = page.url.lower()

                if "ozon.ru" in url:
                    result.append(("ozon", page))
                elif "wildberries.ru" in url:
                    result.append(("wb", page))
            except:
                continue
        return result

    def parse_marketplace_page(self, page):
        return self.parse_page_text(page)

    def parse_open_pages(self):

        result = []
        pages = (self.get_marketplace_pages())
        for marketplace, page in pages:
            try:
                    data = self.parse_marketplace_page(page)
                    result.append(data)
            except Exception as e:
                print(f"Ошибка: {e}")
        return result

    def start_network_logger(self, page):

        captured = []

        def on_request(request):
            try:
                if request.resource_type in ("xhr", "fetch"):
                    data = {
                        "type": "request",
                        "method": request.method,
                        "url": request.url,
                        "resource_type": request.resource_type,
                    }
                    try:
                        data["post_data"] = request.post_data
                    except Exception:
                        data["post_data"] = None

                    captured.append(data)

                    print(
                        "\n[API REQUEST]"
                        f"\n{request.method} {request.url}"
                    )
                    if request.post_data:
                        print(
                            f"POST DATA: "
                            f"{request.post_data[:1000]}"
                        )
            except Exception as e:
                print(
                    f"[NETWORK REQUEST ERROR] {e}"
                )

        def on_response(response):
            try:
                request = response.request

                if request.resource_type not in (
                        "xhr",
                        "fetch",
                ):
                    return

                print(
                    "\n[API RESPONSE]"
                    f"\n{response.status} "
                    f"{response.url}"
                )
                data = {
                    "type": "response",
                    "status": response.status,
                    "url": response.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                }
                try:
                    content_type = (
                        response.headers.get(
                            "content-type",
                            ""
                        )
                    )
                    if (
                            "application/json"
                            in content_type.lower()
                    ):
                        body = response.json()

                        data["body"] = body

                        print(
                            "[JSON RESPONSE]"
                        )

                        print(
                            str(body)[:3000]
                        )
                    else:
                        body = response.text()

                        data["body"] = body

                        print(
                            "[TEXT RESPONSE]"
                        )

                        print(
                            body[:2000]
                        )
                except Exception as e:
                    print(
                        f"[BODY ERROR] {e}"
                    )
                captured.append(data)

            except Exception as e:
                print(
                    f"[NETWORK RESPONSE ERROR] {e}"
                )
        page.on(
            "request",
            on_request
        )
        page.on(
            "response",
            on_response
        )
        return captured

    def inspect_url_network(self, url):

        page = None

        try:
            print(
                "\n"
                "========================================"
            )
            print(
                "NETWORK INSPECT:"
            )
            print(url)
            print(
                "========================================"
            )
            page = self.context.new_page()
            page.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in (
                        "image",
                        "media",
                        "font",
                        "stylesheet",
                    )
                    else route.continue_()
                ),
            )
            captured = (
                self.start_network_logger(
                    page
                )
            )
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            try:
                page.wait_for_load_state(
                    "networkidle",
                    timeout=10000,
                )
            except Exception:
                pass

            page.wait_for_timeout(3000)

            print(
                "\n"
                "========================================"
            )
            print(
                "CAPTURED API REQUESTS:"
            )
            print(
                "========================================"
            )
            seen = set()

            for item in captured:
                if item.get("type") != "request":
                    continue

                method = item.get(
                    "method"
                )
                request_url = item.get(
                    "url"
                )
                key = (
                    method,
                    request_url,
                )
                if key in seen:
                    continue

                seen.add(key)

                print(
                    f"\n{method} {request_url}"
                )
            print(
                "\n"
                "========================================"
            )
            print(
                f"TOTAL UNIQUE REQUESTS: "
                f"{len(seen)}"
            )
            print(
                "========================================"
            )
            with open(
                    "network_capture.json",
                    "w",
                    encoding="utf-8",
            ) as f:

                json.dump(
                    captured,
                    f,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            print(
                "\nNETWORK CAPTURE SAVED:"
                "\nnetwork_capture.json"
            )
            return captured

        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
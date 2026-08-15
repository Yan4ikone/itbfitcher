import inspect
import logging
import os
import random
import subprocess
import time


import requests
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

from parser.ozon_html_parser import (
    parse_ozon_page_async,
)

from engines.image_description_engine import ImageDescriptionEngine
from parser.ozon_html_parser import parse_ozon_page
from parser.ozon_parser import OzonParser
from parser.wb_parser import WBParser
from models.card_builder import build_product_card
from processors.card_image_processor import CardImageProcessor
from services.image_description_service import ImageDescriptionService

log = logging.getLogger(__name__)

# Ресурсы, которые блокируем при загрузке карточки товара: парсер читает
# только HTML/JSON (ld+json, dl/dt/dd), картинки/шрифты/css/медиа ему не
# нужны и их загрузка - основная причина медленного открытия страницы.
BLOCKED_RESOURCE_TYPES = ("media", "font", "stylesheet", "image")


class CDPProductParser:

    def __init__(self, cdp_url="http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        image_engine = ImageDescriptionEngine()
        image_service = ImageDescriptionService(image_engine)
        self.image_processor = CardImageProcessor(image_service)

    # ------------------------------------------------------------------
    # BROWSER LIFECYCLE
    # ------------------------------------------------------------------

    def kill_yandex_browser(self):
        subprocess.run(
            ["taskkill", "/F", "/IM", "browser.exe"],
            capture_output=True,
        )
        time.sleep(2)

    def is_cdp_running(self):
        try:
            requests.get("http://127.0.0.1:9222/json/version", timeout=2)
            return True
        except requests.RequestException:
            return False

    def start_yandex_browser(self):
        browser_path = r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe"
        if not os.path.exists(browser_path):
            raise RuntimeError("Не найден Яндекс.Браузер")

        subprocess.Popen([browser_path, "--remote-debugging-port=9222"])

        for _ in range(20):
            if self.is_cdp_running():
                return
            time.sleep(1)

        raise RuntimeError("Не удалось запустить CDP порт 9222")

    def connect(self):
        if not self.is_cdp_running():
            self.start_yandex_browser()

        self.playwright = sync_playwright().start()

        try:
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
        except Exception:
            log.warning("Не удалось подключиться по CDP, перезапускаю браузер", exc_info=True)
            self.kill_yandex_browser()
            self.start_yandex_browser()
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)

        if not self.browser.contexts:
            raise RuntimeError("Не найден ни один контекст браузера")

        self.context = self.browser.contexts[0]
        log.info("CDP подключен")

    async def connect_async(self):
        """
        Одно асинхронное Playwright/CDP-соединение
        с уже работающим Yandex Browser.

        ВАЖНО:
        Этот объект должен использоваться только внутри
        одного asyncio event loop.
        """

        if not self.is_cdp_running():
            self.start_yandex_browser()

        self.async_playwright = (
            await async_playwright().start()
        )

        try:

            self.async_browser = (
                await self.async_playwright.chromium.connect_over_cdp(
                    self.cdp_url
                )
            )

        except Exception:

            log.warning(
                "Не удалось подключиться по CDP, "
                "перезапускаю браузер",
                exc_info=True,
            )

            try:
                await self.async_playwright.stop()
            except Exception:
                pass

            self.kill_yandex_browser()
            self.start_yandex_browser()

            self.async_playwright = (
                await async_playwright().start()
            )

            self.async_browser = (
                await self.async_playwright.chromium.connect_over_cdp(
                    self.cdp_url
                )
            )

        if not self.async_browser.contexts:
            raise RuntimeError(
                "Не найден ни один контекст браузера"
            )

        self.async_context = (
            self.async_browser.contexts[0]
        )

        log.info(
            "Async CDP подключен"
        )

    async def parse_url_async(
            self,
            page,
            url,
            timeout=30000,
    ):
        """
        Парсит URL в уже существующей вкладке.

        Вкладка НЕ создаётся и НЕ закрывается здесь.

        Один worker получает одну постоянную page
        и использует её для последовательной обработки
        своих URL.
        """

        log.info(
            "OZON OPEN: %s",
            url,
        )

        # ======================================================
        # Навигация
        # ======================================================

        try:

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout,
            )

        except Exception as exc:

            log.warning(
                "Таймаут/ошибка перехода по URL: %s",
                url,
                exc_info=True,
            )

            # --------------------------------------------------
            # Не создаём новую вкладку.
            #
            # Останавливаем текущую навигацию.
            # --------------------------------------------------

            try:
                await page.evaluate(
                    "() => window.stop()"
                )
            except Exception:
                pass

            # --------------------------------------------------
            # Сбрасываем текущую страницу.
            # Это та же самая вкладка.
            # --------------------------------------------------

            try:

                await page.goto(
                    "about:blank",
                    wait_until="commit",
                    timeout=5000,
                )

            except Exception:

                log.debug(
                    "Не удалось сбросить страницу "
                    "на about:blank",
                    exc_info=True,
                )

            # --------------------------------------------------
            # Одна повторная попытка
            # --------------------------------------------------

            try:

                log.info(
                    "Повторный переход: %s",
                    url,
                )

                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )

            except Exception:

                log.exception(
                    "Повторный переход не удался: %s",
                    url,
                )

                raise

        # ======================================================
        # Парсим DOM
        # ======================================================

        data = await parse_ozon_page_async(
            page
        )

        # ======================================================
        # ProductCard
        # ======================================================

        card = build_product_card(
            url,
            data,
            raw_text=data.get(
                "description",
                "",
            ),
        )

        log.info(
            "Карточка построена: "
            "TITLE=%s "
            "DESCRIPTION=%d "
            "SPECS=%d "
            "IMAGES=%d",
            bool(card.title),
            len(
                card.description
                or ""
            ),
            len(
                data.get(
                    "specs",
                    {},
                )
            ),
            len(
                data.get(
                    "images",
                    [],
                )
            ),
        )

        return card

    async def disconnect_async(
            self,
            close_browser=False,
    ):
        """
        Закрывает async Playwright.
        close_browser=True используется только
        после завершения всей обработки.
        """

        try:

            if close_browser:

                if getattr(
                        self,
                        "async_browser",
                        None,
                ):

                    try:

                        await self.async_browser.close()

                    except Exception:

                        log.debug(
                            "Ошибка закрытия async browser",
                            exc_info=True,
                        )

        finally:

            try:

                if getattr(
                        self,
                        "async_playwright",
                        None,
                ):
                    await self.async_playwright.stop()

            except Exception:

                log.debug(
                    "Ошибка остановки async Playwright",
                    exc_info=True,
                )

            self.async_browser = None
            self.async_context = None
            self.async_playwright = None

    def disconnect(self, close_browser=False):
        """
        Останавливает только Playwright-соединение текущего потока.

        При многопоточности несколько CDPProductParser подключаются
        к одному браузеру. Поэтому worker не должен закрывать общий браузер.

        close_browser=True используется только главным parser после
        завершения всей обработки.
        """

        if close_browser:
            try:
                if self.browser:
                    self.browser.close()
            except Exception:
                log.debug(
                    "Ошибка при закрытии браузера",
                    exc_info=True,
                )

        try:
            if getattr(self, "playwright", None):
                self.playwright.stop()
        except Exception:
            log.debug(
                "Ошибка при остановке playwright",
                exc_info=True,
            )

        self.browser = None
        self.context = None
        self.playwright = None

    # ------------------------------------------------------------------
    # PAGE LOOKUP / OPEN
    # ------------------------------------------------------------------

    def find_page_by_url(self, url):
        for page in self.context.pages:
            try:
                if url.lower() in page.url.lower():
                    return page
            except Exception:
                continue
        return None

    def open_url(self, url, timeout=30000):
        """
        Открывает новую вкладку и переходит по url.
        Блокирует тяжёлые ресурсы (картинки/шрифты/css/медиа) - парсеру
        нужен только DOM и встроенный JSON, визуальный рендер не важен.
        Не делает дополнительных ожиданий (networkidle и т.п.) - это
        задача вызывающего кода (см. parse_ozon_page), который ждёт
        именно то, что ему нужно, а не абстрактную "тишину сети".
        """
        page = self.context.new_page()

        def route_handler(route):
            try:
                if route.request.resource_type in BLOCKED_RESOURCE_TYPES:
                    route.abort()
                else:
                    route.continue_()
            except Exception:
                # Страница могла закрыться/перейти по другому адресу
                # раньше, чем долетел ответ маршрутизатора - это не
                # ошибка бизнес-логики, просто гонка Playwright.
                try:
                    route.continue_()
                except Exception:
                    pass

        page.route("**/*", route_handler)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except Exception:
            log.warning("Таймаут при переходе по URL: %s", url, exc_info=True)
            # Страница может быть частично пригодна для парсинга,
            # даже если goto не дождался domcontentloaded.

        return page

    def parse_url(self, url):
        """
        Парсит одну страницу Ozon.

        В многопоточном режиме каждая попытка использует
        отдельную вкладку.

        Если Ozon зависает на навигации:
            1. закрываем зависшую вкладку;
            2. создаём новую;
            3. повторяем запрос.

        Если после повторной попытки страница не загрузилась —
        выбрасываем исключение, чтобы worker мог перейти
        к следующей задаче.
        """

        max_attempts = 2

        last_error = None

        for attempt in range(
                1,
                max_attempts + 1
        ):

            page = None

            try:

                log.info(
                    "OZON OPEN "
                    "attempt=%s/%s "
                    "URL=%s",
                    attempt,
                    max_attempts,
                    url,
                )
                page = self.context.new_page()
                # ==================================================
                # БЛОКИРОВКА НЕНУЖНЫХ РЕСУРСОВ
                # ==================================================
                def route_handler(route):

                    try:
                        if (
                                route.request.resource_type
                                in BLOCKED_RESOURCE_TYPES
                        ):
                            route.abort()

                        else:

                            route.continue_()

                    except Exception:
                        try:
                            route.continue_()
                        except Exception:
                            pass

                page.route(
                    "**/*",
                    route_handler,
                )

                # ==================================================
                # NAVIGATION
                # ==================================================

                try:

                    response = page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )

                except Exception as exc:

                    last_error = exc

                    log.warning(
                        "OZON NAVIGATION ERROR "
                        "attempt=%s/%s "
                        "URL=%s: %s",
                        attempt,
                        max_attempts,
                        url,
                        exc,
                    )

                    # ----------------------------------------------
                    # Закрываем зависшую вкладку
                    # ----------------------------------------------

                    try:

                        page.close()

                    except Exception:

                        log.debug(
                            "Не удалось закрыть "
                            "зависшую страницу",
                            exc_info=True,
                        )

                    page = None

                    # ----------------------------------------------
                    # Если есть ещё попытка — повторяем
                    # ----------------------------------------------

                    if attempt < max_attempts:
                        time.sleep(
                            random.uniform(
                                1.0,
                                2.0,
                            )
                        )

                        continue

                    raise

                # ==================================================
                # ПРОВЕРКА СТРАНИЦЫ
                # ==================================================

                try:

                    current_url = page.url

                except Exception:

                    current_url = ""

                log.info(
                    "OZON PAGE URL: %s",
                    current_url,
                )

                # --------------------------------------------------
                # Иногда Ozon возвращает пустую страницу.
                #
                # Проверяем body.
                # --------------------------------------------------

                try:

                    body_text = page.locator(
                        "body"
                    ).inner_text(
                        timeout=5000
                    ).strip()

                except Exception:

                    body_text = ""

                # --------------------------------------------------
                # Пустая страница
                # --------------------------------------------------

                if not body_text:

                    last_error = RuntimeError(
                        "Ozon returned empty page"
                    )

                    log.warning(
                        "OZON EMPTY PAGE "
                        "attempt=%s/%s "
                        "URL=%s",
                        attempt,
                        max_attempts,
                        url,
                    )

                    try:

                        page.close()

                    except Exception:

                        log.debug(
                            "Не удалось закрыть "
                            "пустую страницу",
                            exc_info=True,
                        )

                    page = None

                    if attempt < max_attempts:
                        time.sleep(
                            random.uniform(
                                1.0,
                                2.0,
                            )
                        )

                        continue

                    raise last_error

                # ==================================================
                # PARSING
                # ==================================================

                data = parse_ozon_page(
                    page
                )

                # ==================================================
                # PRODUCT CARD
                # ==================================================

                card = build_product_card(
                    url,
                    data,
                    raw_text=data.get(
                        "description",
                        "",
                    ),
                )

                log.info(
                    "Карточка построена: "
                    "TITLE=%s "
                    "DESCRIPTION=%d "
                    "SPECS=%d "
                    "IMAGES=%d",
                    bool(card.title),
                    len(
                        card.description
                        or ""
                    ),
                    len(
                        data.get(
                            "specs",
                            {},
                        )
                    ),
                    len(
                        data.get(
                            "images",
                            [],
                        )
                    ),
                )

                return card

            except Exception:

                last_error = (
                        last_error
                        or RuntimeError(
                    "Ozon parse failed"
                )
                )

                log.exception(
                    "OZON PARSE ERROR "
                    "attempt=%s/%s "
                    "URL=%s",
                    attempt,
                    max_attempts,
                    url,
                )

                # --------------------------------------------------
                # Если page ещё существует — закрываем
                # --------------------------------------------------

                if page is not None:

                    try:

                        page.close()

                    except Exception:

                        log.debug(
                            "Ошибка закрытия page",
                            exc_info=True,
                        )

                # --------------------------------------------------
                # Если есть retry
                # --------------------------------------------------

                if attempt < max_attempts:
                    time.sleep(
                        random.uniform(
                            1.0,
                            2.0,
                        )
                    )

                    continue

                raise last_error
        return None

    # ------------------------------------------------------------------
    # LEGACY / MULTI-MARKETPLACE PATH (уже открытые вкладки в браузере)
    # ------------------------------------------------------------------

    def wait_page_ready(self, page):
        try:
            page.wait_for_load_state("networkidle", timeout=7000)
        except Exception:
            log.debug("networkidle не наступил вовремя", exc_info=True)

    def parse_page_text(self, page):
        url = page.url.lower()

        if "wildberries.ru" in url:
            parser = WBParser()
        else:
            parser = OzonParser()

        log.debug("Используется парсер: %s", inspect.getfile(type(parser)))

        parsed = parser.parse_page(page)

        try:
            page.evaluate("() => window.stop()")
        except Exception:
            log.debug("Не удалось остановить загрузку страницы", exc_info=True)

        card = build_product_card(page.url, parsed, parsed["raw_text"])
        log.info(
            "Карточка построена (legacy): TITLE=%s DESCRIPTION=%d IMAGES=%d",
            bool(card.title),
            len(card.description or ""),
            len(card.images),
        )
        return card

    def get_marketplace_pages(self):
        result = []
        for page in self.context.pages:
            try:
                url = page.url.lower()
                if "ozon.ru" in url:
                    result.append(("ozon", page))
                elif "wildberries.ru" in url:
                    result.append(("wb", page))
            except Exception:
                continue
        return result

    def parse_marketplace_page(self, page):
        return self.parse_page_text(page)

    def parse_open_pages(self):
        result = []
        for marketplace, page in self.get_marketplace_pages():
            try:
                result.append(self.parse_marketplace_page(page))
            except Exception:
                log.exception("Ошибка при парсинге открытой вкладки: %s", marketplace)
        return result

    # ------------------------------------------------------------------
    # DEBUG-ONLY: ручная инспекция сетевых запросов страницы.
    # Не используется в основном пайплайне. Пишет захваченные запросы/
    # ответы в network_capture.json. Печатает только итог, не каждый
    # запрос - если нужен подробный вывод при отладке, включите DEBUG
    # уровень логирования для этого модуля.
    # ------------------------------------------------------------------

    def inspect_url_network(self, url, out_file="network_capture.json"):
        import json

        captured = []
        page = None

        def on_request(request):
            if request.resource_type not in ("xhr", "fetch"):
                return
            try:
                captured.append({
                    "type": "request",
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "post_data": request.post_data,
                })
            except Exception:
                log.debug("Не удалось прочитать request", exc_info=True)

        def on_response(response):
            request = response.request
            if request.resource_type not in ("xhr", "fetch"):
                return
            try:
                content_type = response.headers.get("content-type", "")
                body = response.json() if "application/json" in content_type.lower() else response.text()
            except Exception:
                body = None

            captured.append({
                "type": "response",
                "status": response.status,
                "url": response.url,
                "method": request.method,
                "body": body,
            })

        try:
            page = self.context.new_page()
            page.route(
                "**/*",
                lambda route: route.abort()
                if route.request.resource_type in ("image", "media", "font", "stylesheet")
                else route.continue_(),
            )
            page.on("request", on_request)
            page.on("response", on_response)

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(3000)

            unique_requests = {
                (item["method"], item["url"]): item
                for item in captured
                if item.get("type") == "request"
            }

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(captured, f, ensure_ascii=False, indent=2, default=str)

            log.info(
                "Сетевая инспекция сохранена: %s (%d уникальных запросов)",
                out_file,
                len(unique_requests),
            )
            return captured
        finally:
            if page:
                try:
                    page.close()
                except Exception:
                    pass
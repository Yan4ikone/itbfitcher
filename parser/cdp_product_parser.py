import logging
import os
import subprocess
import time

import requests
from playwright.async_api import async_playwright

from engines.image_description_engine import ImageDescriptionEngine
from models.card_builder import build_product_card
from parser.ozon_html_parser import (
    parse_ozon_page_async,
)
from parser.wb_parser import WBParser
from processors.card_image_processor import CardImageProcessor
from services.image_description_service import ImageDescriptionService

log = logging.getLogger(__name__)

# Ресурсы, которые блокируем при загрузке карточки товара
BLOCKED_RESOURCE_TYPES = ("media", "font", "stylesheet", "image")
# (таймаут / временная сетевая ошибка / антибот-заглушка).
GOTO_MAX_ATTEMPTS = 3
# Пауза между повторными попытками.
GOTO_RETRY_DELAY = 1.5


class CDPProductParser:

    def __init__(self, cdp_url="http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        image_engine = ImageDescriptionEngine()
        image_service = ImageDescriptionService(image_engine)
        self.image_processor = CardImageProcessor(image_service)
        self.wb_parser = WBParser()
        self._wb_responses = {}
        self.async_playwright = None
        self.async_browser = None
        self.async_context = None
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
        browser_path = (
            r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe"
        )
        if not os.path.exists(browser_path):
            raise RuntimeError(
                f"Не найден Яндекс.Браузер: {browser_path}"
            )
        # Отдельный профиль для автоматизации
        user_data_dir = r"C:\Users\Yan\AppData\Local\YandexAutomationProfile"
        profile_directory = "Default"
        profile_path = os.path.join(user_data_dir, profile_directory)
        os.makedirs(profile_path, exist_ok=True)
        log.info("Запускаем Yandex Browser (автоматизационный профиль)")
        log.info(
            "User Data: %s",
            user_data_dir,
        )
        log.info(
            "Profile: %s",
            profile_directory,
        )
        subprocess.Popen(
            [
                browser_path,
                "--remote-debugging-port=9222",
                "--remote-debugging-address=127.0.0.1",
                f"--user-data-dir={user_data_dir}",
                f"--profile-directory={profile_directory}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for attempt in range(30):

            if self.is_cdp_running():
                log.info(
                    "CDP 9222 доступен "
                    "(попытка %d/30)",
                    attempt + 1,
                )
                return

            time.sleep(1)

        raise RuntimeError(
            "Yandex Browser запущен, "
            "но CDP 9222 не стал доступен за 30 секунд"
        )
    async def connect_async(self):
        """
        Подключение к уже работающему Yandex Browser.
        Если CDP 9222 уже доступен — НИЧЕГО не запускаем.
        Если CDP отсутствует — запускаем Yandex и ждём CDP.
        """
        if not self.is_cdp_running():
            log.info(
                "CDP 9222 не найден. "
                "Запускаем Yandex Browser."
            )
            self.start_yandex_browser()

        else:
            log.info(
                "CDP 9222 уже работает. "
                "Используем существующий Yandex Browser."
            )
        self.async_playwright = (await async_playwright().start())
        self.async_browser = (
            await self.async_playwright.chromium.connect_over_cdp(self.cdp_url))
        if not self.async_browser.contexts:
            raise RuntimeError("CDP подключён, но BrowserContext отсутствует")
        self.async_context = (self.async_browser.contexts[0])

        # Защита от "осиротевшего" подключения: если сразу после
        # connect_over_cdp вкладок 0 - порт 9222, вероятно, отвечает
        # от более раннего, уже мёртвого процесса. Ждём и перепроверяем,
        # при необходимости перезапускаем браузер с нуля.
        if not self.async_context.pages:
            log.warning(
                "Сразу после подключения 0 вкладок - "
                "возможно, порт 9222 отвечает от старого процесса. "
                "Жду 1.5 сек и перепроверяю..."
            )
            import asyncio
            await asyncio.sleep(1.5)

            if not self.async_context.pages:
                log.error(
                    "Вкладок всё ещё нет. Похоже, CDP-подключение "
                    "ведёт к осиротевшему процессу браузера. "
                    "Перезапускаю browser.exe с нуля."
                )
                try:
                    await self.async_browser.close()
                except Exception:
                    pass
                try:
                    await self.async_playwright.stop()
                except Exception:
                    pass

                self.kill_yandex_browser()
                self.start_yandex_browser()
                self.async_playwright = await async_playwright().start()
                self.async_browser = (
                    await self.async_playwright.chromium.connect_over_cdp(
                        self.cdp_url
                    )
                )
                if not self.async_browser.contexts:
                    raise RuntimeError(
                        "CDP подключён повторно, но BrowserContext "
                        "всё равно отсутствует"
                    )
                self.async_context = self.async_browser.contexts[0]

                if not self.async_context.pages:
                    raise RuntimeError(
                        "После перезапуска браузера вкладок всё ещё "
                        "нет. Проверьте вручную: не открыт ли где-то "
                        "ваш ОБЫЧНЫЙ Yandex Browser с тем же "
                        "user-data-dir."
                    )
        log.info(
            "CDP подключён. "
            "Contexts=%d Pages=%d",
            len(self.async_browser.contexts),
            len(self.async_context.pages),
        )
        for index, page in enumerate(
                self.async_context.pages,
                start=1,
        ):
            try:
                log.info(
                    "CDP PAGE %d: %s",
                    index,
                    page.url,
                )
            except Exception:
                pass

    def _attach_wb_response_listener(self, page):
        """
        Перехватывает JSON/XHR/fetch ответы WB непосредственно
        из Playwright network layer.
        """

        self._wb_responses[page] = []

        async def handle_response(response):

            try:
                request = response.request

                resource_type = request.resource_type

                if resource_type not in ("xhr", "fetch"):
                    return

                url = response.url

                # Не собираем служебный мусор
                low = url.lower()

                if any(
                        x in low
                        for x in (
                                "sentry",
                                "antibot",
                                "find-frontend-settings",
                        )
                ):
                    return

                print(
                    f"[WB NETWORK] "
                    f"{response.status} "
                    f"{resource_type} "
                    f"{url}"
                )

                try:
                    content_type = (
                        response.headers.get(
                            "content-type",
                            ""
                        ).lower()
                    )
                except Exception:
                    content_type = ""

                # Нас интересует JSON
                if (
                        "json" not in content_type
                        and not url.lower().endswith(".json")
                ):
                    return

                try:
                    body = await response.json()
                except Exception:
                    return

                if body:
                    self._wb_responses[page].append({
                        "url": url,
                        "status": response.status,
                        "data": body,
                    })

                    print(
                        "[WB NETWORK JSON] FOUND:",
                        url
                    )

            except Exception:
                log.debug(
                    "WB response listener error",
                    exc_info=True,
                )

        page.on(
            "response",
            handle_response,
        )

    async def _goto_with_retry(self, page, url, timeout):

        import asyncio

        last_exc = None

        for attempt in range(1, GOTO_MAX_ATTEMPTS + 1):
            try:
                await page.goto(
                    url,
                    wait_until="commit",
                    timeout=timeout,
                )
                return
            except Exception as exc:
                last_exc = exc
                log.warning(
                    "Переход не удался (попытка %d/%d): %s",
                    attempt,
                    GOTO_MAX_ATTEMPTS,
                    url,
                    exc_info=True,
                )
                if attempt < GOTO_MAX_ATTEMPTS:
                    await asyncio.sleep(GOTO_RETRY_DELAY)

        log.error(
            "Не удалось перейти по URL после %d попыток: %s",
            GOTO_MAX_ATTEMPTS,
            url,
        )
        raise last_exc

    async def parse_url_async(self, page, url, timeout=30000):
        """
        Парсит URL в уже существующей вкладке.
        Ozon и Wildberries используют разные HTML/API-парсеры,
        но дальше обе карточки проходят через один build_product_card().
        """
        url_lower = (url or "").lower()
        is_wb = (
                "wildberries.ru" in url_lower
                or "wb.ru" in url_lower
        )
        marketplace = "WB" if is_wb else "OZON"
        log.info(
            "%s OPEN: %s",
            marketplace,
            url,
        )
        # --------------------------------------------------
        # OPEN
        # --------------------------------------------------
        if is_wb:
            await self._goto_with_retry(page, url, timeout)
        # ==================================================
        # WILDBERRIES
        # ==================================================

        if is_wb:

            log.info(
                "WB PARSER: начинаем разбор %s",
                page.url or url,
            )
            responses = self._wb_responses.get(
                page,
                []
            )
            log.info(
                "WB NETWORK RESPONSES: %d",
                len(responses),
            )
            data = await self.wb_parser.parse_page(
                page,
                responses=responses,
            )
            log.info(
                "WB PARSED: TITLE=%s DESCRIPTION=%d SPECS=%d",
                bool(data.get("title")),
                len(data.get("description", "") or ""),
                len(data.get("specs", {}) or {}),
            )
        # ==================================================
        # OZON
        # ==================================================
        else:

            data = await parse_ozon_page_async(page)
            log.info(
                "OZON PARSED: TITLE=%s DESCRIPTION=%d SPECS=%d",
                bool(data.get("title")),
                len(data.get("description", "") or ""),
                len(data.get("specs", {}) or {}),
            )
        # --------------------------------------------------
        # BUILD CARD
        # --------------------------------------------------
        # ВАЖНО:
        # используем фактический URL после редиректа.
        final_url = page.url or url
        card = build_product_card(final_url, data,
            raw_text=data.get("raw_text", "")
                     or data.get("description", ""),
        )
        log.info(
            "%s CARD BUILT: TITLE=%s DESCRIPTION=%d SPECS=%d",
            marketplace,
            bool(card.title),
            len(card.description or ""),
            len(data.get("specs", {}) or {}),
        )
        return card

    async def disconnect_async(self, close_browser=False):
        """
        Закрывает async Playwright.
        close_browser=True используется только
        после завершения всей обработки.
        """
        try:
            if close_browser:
                if getattr(self, "async_browser", None):
                    try:
                        await self.async_browser.close()

                    except Exception:

                        log.debug("Ошибка закрытия async browser", exc_info=True)
        finally:
            try:
                if getattr(self, "async_playwright", None):
                    await self.async_playwright.stop()
            except Exception:

                log.debug("Ошибка остановки async Playwright", exc_info=True)
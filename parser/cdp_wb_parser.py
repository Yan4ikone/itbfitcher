import logging
import os
import subprocess
import time

import requests
from playwright.async_api import async_playwright

from models.card_builder import build_product_card
from parser.wb_parser import WBParser

log = logging.getLogger(__name__)

GOTO_MAX_ATTEMPTS = 3
GOTO_RETRY_DELAY = 1.5


class CDPWBParser:

    def __init__(self, cdp_url="http://127.0.0.1:9222"):

        self.cdp_url = cdp_url

        self.parser = WBParser()

        self.async_playwright = None
        self.async_browser = None
        self.async_context = None

    # ==========================================================
    # BROWSER LIFECYCLE
    # ==========================================================

    def kill_yandex_browser(self):

        subprocess.run(
            ["taskkill", "/F", "/IM", "browser.exe"],
            capture_output=True,
        )

        time.sleep(2)

    def is_cdp_running(self):

        try:

            requests.get(
                "http://127.0.0.1:9222/json/version",
                timeout=2,
            )

            return True

        except requests.RequestException:

            return False

    def start_yandex_browser(self):

        browser_path = (
            r"C:\Program Files\Yandex\YandexBrowser"
            r"\Application\browser.exe"
        )

        if not os.path.exists(browser_path):

            raise RuntimeError(
                f"Не найден Яндекс.Браузер: {browser_path}"
            )

        user_data_dir = (
            r"C:\Users\Yan\AppData\Local"
            r"\YandexAutomationProfile"
        )

        profile_directory = "Default"

        profile_path = os.path.join(
            user_data_dir,
            profile_directory,
        )

        os.makedirs(
            profile_path,
            exist_ok=True,
        )

        log.info(
            "Запускаем Yandex Browser "
            "для WB"
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
            "но CDP 9222 не стал доступен "
            "за 30 секунд"
        )

    async def connect_async(self):

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

        self.async_playwright = (
            await async_playwright().start()
        )

        self.async_browser = (
            await self.async_playwright
            .chromium
            .connect_over_cdp(self.cdp_url)
        )

        if not self.async_browser.contexts:

            raise RuntimeError(
                "CDP подключён, "
                "но BrowserContext отсутствует"
            )

        self.async_context = (
            self.async_browser.contexts[0]
        )

        if not self.async_context.pages:

            log.warning(
                "После подключения нет вкладок. "
                "Ждём 1.5 сек..."
            )

            import asyncio

            await asyncio.sleep(1.5)

            if not self.async_context.pages:

                log.error(
                    "Вкладок всё ещё нет. "
                    "Перезапускаем браузер."
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

                self.async_playwright = (
                    await async_playwright().start()
                )

                self.async_browser = (
                    await self.async_playwright
                    .chromium
                    .connect_over_cdp(
                        self.cdp_url
                    )
                )

                if not self.async_browser.contexts:

                    raise RuntimeError(
                        "После перезапуска "
                        "BrowserContext отсутствует"
                    )

                self.async_context = (
                    self.async_browser.contexts[0]
                )

                if not self.async_context.pages:

                    raise RuntimeError(
                        "После перезапуска браузера "
                        "вкладок всё ещё нет."
                    )

        log.info(
            "WB CDP подключён. "
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
                    "WB CDP PAGE %d: %s",
                    index,
                    page.url,
                )

            except Exception:
                pass

    # ==========================================================
    # NAVIGATION
    # ==========================================================

    async def _goto_with_retry(
        self,
        page,
        url,
        timeout,
    ):

        import asyncio

        last_exc = None

        for attempt in range(
            1,
            GOTO_MAX_ATTEMPTS + 1,
        ):

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
                    "WB переход не удался "
                    "(попытка %d/%d): %s",
                    attempt,
                    GOTO_MAX_ATTEMPTS,
                    url,
                    exc_info=True,
                )

                if attempt < GOTO_MAX_ATTEMPTS:

                    await asyncio.sleep(
                        GOTO_RETRY_DELAY
                    )

        log.error(
            "WB: не удалось перейти "
            "по URL после %d попыток: %s",
            GOTO_MAX_ATTEMPTS,
            url,
        )

        raise last_exc

    # ==========================================================
    # PARSE URL
    # ==========================================================

    async def parse_url_async(
        self,
        page,
        url,
        timeout=30000,
    ):
        """
        Одна постоянная вкладка на worker.

        URL:
            WB
             ↓
        page.goto()
             ↓
        WBParser.parse_page(page)
             ↓
        build_product_card()
             ↓
        ProductCard
        """

        log.info(
            "WB OPEN: %s",
            url,
        )

        await self._goto_with_retry(
            page,
            url,
            timeout,
        )

        # ------------------------------------------------------
        # Даём WB немного времени дорисовать карточку.
        # Не делаем фиксированную длинную задержку.
        # Ждём появления h1 или body.
        # ------------------------------------------------------

        try:

            await page.locator(
                "body"
            ).wait_for(
                state="visible",
                timeout=5000,
            )

        except Exception:

            log.debug(
                "WB body не дождались",
                exc_info=True,
            )

        # ------------------------------------------------------
        # WB HTML parser
        # ------------------------------------------------------

        data = self.parser.parse_page(page)

        if not data:

            raise RuntimeError(
                "WBParser вернул пустой результат"
            )

        final_url = page.url or url

        # ------------------------------------------------------
        # Строим общую ProductCard.
        # Именно её дальше понимает существующий
        # DecisionEngine.
        # ------------------------------------------------------

        card = build_product_card(
            final_url,
            data,
            raw_text=data.get(
                "raw_text",
                "",
            ),
        )

        log.info(
            "WB карточка построена: "
            "TITLE=%s "
            "DESCRIPTION=%d "
            "SPECS=%d",
            bool(card.title),
            len(card.description or ""),
            len(data.get("specs", {})),
        )

        return card

    # ==========================================================
    # DISCONNECT
    # ==========================================================

    async def disconnect_async(
        self,
        close_browser=False,
    ):

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
                            "Ошибка закрытия "
                            "WB async browser",
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
                    "Ошибка остановки "
                    "WB async Playwright",
                    exc_info=True,
                )
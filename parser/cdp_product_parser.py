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

        # ВАЖНО: НЕ используем повседневный профиль пользователя.
        # Если параллельно открыт обычный Yandex Browser с тем же
        # user-data-dir, Chromium просто активирует существующее окно
        # и ПОЛНОСТЬЮ ИГНОРИРУЕТ новые флаги командной строки (включая
        # --remote-debugging-port). В таком случае скрипт по факту
        # подключается к порту 9222 от какого-то более раннего,
        # осиротевшего процесса без реальных вкладок - отсюда
        # "Существующих вкладок: 0" и ошибка при создании новой вкладки.
        #
        # Отдельный профиль для автоматизации решает проблему раз
        # и навсегда: один раз залогиньтесь на Ozon в этом профиле
        # вручную (запустите browser.exe с этим же --user-data-dir
        # БЕЗ --remote-debugging-port и залогиньтесь), дальше сессия
        # сохранится, и конфликтов с обычным браузером не будет,
        # даже если он открыт параллельно на другом профиле.
        user_data_dir = (
            r"C:\Users\Yan\AppData\Local\YandexAutomationProfile"
        )
        profile_directory = "Default"
        profile_path = os.path.join(
            user_data_dir,
            profile_directory,
        )

        os.makedirs(profile_path, exist_ok=True)

        log.info(
            "Запускаем Yandex Browser (автоматизационный профиль)"
        )
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
                # CDP
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
        # --------------------------------------------------
        # Ждём CDP
        # --------------------------------------------------
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
        # --------------------------------------------------
        # Playwright
        # --------------------------------------------------
        self.async_playwright = (
            await async_playwright().start()
        )
        # --------------------------------------------------
        # Подключение к CDP
        # --------------------------------------------------
        self.async_browser = (
            await self.async_playwright.chromium.connect_over_cdp(
                self.cdp_url
            )
        )
        # --------------------------------------------------
        # Контекст
        # --------------------------------------------------
        if not self.async_browser.contexts:
            raise RuntimeError(
                "CDP подключён, но BrowserContext отсутствует"
            )
        self.async_context = (self.async_browser.contexts[0])

        # --------------------------------------------------
        # ЗАЩИТА ОТ "ОСИРОТЕВШЕГО" ПОДКЛЮЧЕНИЯ.
        #
        # Если сразу после connect_over_cdp вкладок 0 - это почти
        # всегда значит, что порт 9222 отвечает от более раннего,
        # уже мёртвого процесса браузера (например, оставшегося от
        # предыдущего запуска скрипта), а не от только что стартовавшего
        # us. Работать с таким контекстом нельзя - new_page() будет
        # падать с "Cannot read properties of undefined (reading
        # '_page')", потому что внутри browser process нет ни одного
        # живого target'а, к которому можно прикрепиться.
        #
        # Даём процессу секунду на то, чтобы создать свою первую
        # вкладку, и перепроверяем. Если и после этого пусто -
        # считаем подключение нерабочим, убиваем browser.exe и
        # заставляем вызывающий код начать заново (переподключиться
        # к чистому процессу).
        # --------------------------------------------------
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
                        "user-data-dir - это блокирует запуск нового "
                        "процесса с флагом --remote-debugging-port."
                    )

        # --------------------------------------------------
        # DEBUG
        # --------------------------------------------------
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

    async def parse_url_async(self, page, url, timeout=30000,):
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
        try:
            await page.goto(
                url,
                wait_until="commit",
                timeout=timeout,
            )
        except Exception as exc:

            log.warning(
                "Таймаут/ошибка перехода по URL: %s",
                url,
                exc_info=True,
            )
            try:
                await page.evaluate(
                    "() => window.stop()"
                )
            except Exception:
                pass
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
            try:

                log.info("Повторный переход: %s", url)
                await page.goto(
                    url,
                    wait_until="commit",
                    timeout=timeout,
                )
            except Exception:

                log.exception(
                    "Повторный переход не удался: %s",
                    url,
                )
                raise

        data = await parse_ozon_page_async(page)
        card = build_product_card(
            url,
            data,
            raw_text=data.get("description", ""))
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
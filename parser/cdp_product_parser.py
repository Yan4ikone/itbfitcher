import os
import subprocess
import time

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

        self.playwright = (
            sync_playwright().start()
        )

        try:

            self.browser = (
                self.playwright.chromium.connect_over_cdp(
                    self.cdp_url
                )
            )

        except Exception:
            self.kill_yandex_browser()
            self.start_yandex_browser()
            self.browser = (
                self.playwright.chromium.connect_over_cdp(
                    self.cdp_url
                )
            )

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

        page = (self.context.new_page())

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        return page

    def wait_page_ready(
            self,
            page
    ):

        try:

            page.wait_for_load_state(
                "networkidle",
                timeout=15000
            )

        except:
            pass

    def parse_page_text(self, page):

        url = page.url.lower()

        if "wildberries.ru" in url:

            parser = WBParser()

        else:

            parser = OzonParser()
        parsed = parser.parse_page(page)
        card = build_product_card(page.url, parsed, parsed["raw_text"])
        print("IMAGES:", card.images[:3])
        card = self.image_processor.process(card)

        return card

    def parse_url(self, url):

        page = None
        created_page = False

        try:

            page = self.find_page_by_url(url)

            if page is None:

                page = self.open_url(url)
                created_page = True

            else:

                page.bring_to_front()
            self.wait_page_ready(page)
            card = self.parse_page_text(page)

            return card

        finally:

            if created_page and page:

                try:
                    page.close()
                except:
                    pass

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

                    result.append(
                        (
                            "ozon",
                            page
                        )
                    )

                elif "wildberries.ru" in url:

                    result.append(
                        (
                            "wb",
                            page
                        )
                    )

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
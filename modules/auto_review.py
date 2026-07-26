from playwright.sync_api import sync_playwright


PROFILE_DIR = "market_profile"


class ProductParser:

    def __init__(self):

        self.playwright = None
        self.context = None
        self.page = None

    # =================================

    def start(self):

        self.playwright = sync_playwright().start()

        self.context = (
            self.playwright.chromium
            .launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=False
            )
        )

        pages = self.context.pages

        if pages:
            self.page = pages[0]
        else:
            self.page = self.context.new_page()

    # =================================

    def stop(self):

        try:
            self.context.close()
        except:
            pass

        try:
            self.playwright.stop()
        except:
            pass

    # =================================

    def parse_product(self, url):

        self.page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        self.page.wait_for_timeout(
            5000
        )

        title = ""

        try:

            title = (
                self.page
                .locator("h1")
                .first
                .inner_text()
            )

        except:

            title = ""

        return {
            "title": title
        }
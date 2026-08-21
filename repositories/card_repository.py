from utils.json_repository import JsonRepository
from utils.url_utils import normalize_ozon_url


class CardRepository(JsonRepository):

    def __init__(self, filename=None):

        if filename is None:
            filename = "storage/runtime_cards.json"

        super().__init__(filename)

        # ==============================================================
        # Индексы для O(1) поиска
        # ==============================================================
        self._slug_index = {}
        self._normalized_url_index = {}
        self._build_indexes()
    # ==============================================================
    # BUILD INDEXES
    # ==============================================================

    def _build_indexes(self):

        self._slug_index.clear()
        self._normalized_url_index.clear()

        for url, item in self.data.items():

            if not isinstance(item, dict):
                continue
            # ----------------------------------------------------------
            # SLUG
            # ----------------------------------------------------------
            slug = (item.get("slug", "")
                or ""
            ).strip().lower()

            if slug:
                self._slug_index[slug] = item
            # ----------------------------------------------------------
            # NORMALIZED URL
            # ----------------------------------------------------------
            normalized_url = (item.get("normalized_url", "")
                or ""
            ).strip()

            if normalized_url:
                self._normalized_url_index[normalized_url] = item
        print(
            "[CardRepository] Индексы построены:",
            f"cards={len(self.data)}",
            f"slugs={len(self._slug_index)}",
            f"normalized_urls={len(self._normalized_url_index)}",
        )
    # ==============================================================
    # FIND BY URL
    # ==============================================================
    def find_by_url(self, url):

        return self.data.get(url)
    # ==============================================================
    # FIND BY NORMALIZED URL
    # ==============================================================
    def find_by_normalized_url(self, url):

        normalized = normalize_ozon_url(url)

        return self._normalized_url_index.get(normalized)
    # ==============================================================
    # FIND BY SLUG
    # ==============================================================
    def find_by_slug(self, slug):

        slug = (slug or "").strip().lower()

        if not slug:
            return None

        return self._slug_index.get(slug)
    # ==============================================================
    # REMEMBER
    # ==============================================================
    def remember(self, card, result=None):

        if not card.url:
            return

        if result is None:
            return

        existing = self.data.get(card.url, {})
        item = {
            "url": card.url,
            "normalized_url":
                normalize_ozon_url(card.url),
            "slug":
                card.slug,
            "title":
                card.title,
            "description":
                card.description,
            "cleaned_text":
                card.cleaned_text,
            "product": (getattr(result, "product", "")
                if result
                else existing.get("product", "")),
            "display_name": (getattr(result, "display_name", "")
                if result
                else existing.get("display_name", "")),
            "code": (getattr(result, "code", "")
                if result
                else existing.get("code", "")),
            "material":
                card.material,
            "quantity":
                card.quantity,
            "brand":
                card.brand,
            "country":
                card.country,
            "specs":
                card.specs,
            "sections":
                card.sections,
            "features":
                card.features,
            "images":
                getattr(card, "images", []),
        }
        # ==============================================================
        # Основное хранилище
        # ==============================================================
        self.data[card.url] = item
        # ==============================================================
        # SLUG INDEX
        # ==============================================================

        slug = (item.get("slug", "") or "").strip().lower()

        if slug:

            self._slug_index[slug] = item
        # ==============================================================
        # NORMALIZED URL INDEX
        # ==============================================================
        normalized_url = (item.get("normalized_url", "") or "").strip()

        if normalized_url:

            self._normalized_url_index[normalized_url] = item
        # ==============================================================
        # JSON DIRTY
        # ==============================================================
        print(
            "[CARD SAVE]",
            card.url,
            "code=",
            getattr(result, "code", ""),
            "product=",
            getattr(result, "product", ""),
        )
        self.mark_dirty()
    # ==============================================================
    # FIND
    # ==============================================================
    def find(self, card):
        # --------------------------------------------------------------
        # 1. Точный URL — O(1)
        # --------------------------------------------------------------
        result = self.find_by_url(card.url)
        if result:
            return result
        # --------------------------------------------------------------
        # 2. Slug — теперь тоже O(1)
        # --------------------------------------------------------------
        if (
            card.slug
            and len(card.slug) > 5
        ):
            result = self.find_by_slug(card.slug)
            if result:
                return result
        return None
    # ==============================================================
    # ALL
    # ==============================================================
    def all(self):

        return self.data.values()
    # ==============================================================
    # REMOVE WITHOUT CODE
    # ==============================================================
    def remove_without_code(self):

        self.data = {
            url: card
            for url, card in self.data.items()
            if card.get("code")
        }
        self._build_indexes()
        self.mark_dirty()
        self.flush()
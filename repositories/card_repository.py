from utils.json_repository import JsonRepository
from utils.url_utils import normalize_ozon_url


class CardRepository(JsonRepository):

    def __init__(self, filename=None):

        if filename is None:
            filename = "storage/runtime_cards.json"

        super().__init__(filename)

    def find_by_url(self, url):
        return self.data.get(url)

    def find_by_normalized_url(self, url):

        normalized = normalize_ozon_url(url)

        for item in self.data.values():

            if item.get("normalized_url") == normalized:
                return item

        return None

    def find_by_slug(self, slug):
        slug = (slug or "").lower()

        for item in self.data.values():

            if item.get("slug", "").lower() == slug:
                return item

        return None

    def remember(self, card, result=None):

        if not card.url:
            return

        if result is None:
            return

        if not getattr(result, "code", ""):
            return

        existing = self.data.get(card.url, {})
        self.data[card.url] = {
            "url": card.url,
            "normalized_url": normalize_ozon_url(card.url),
            "slug": card.slug,
            "title": card.title,
            "description": card.description,
            "cleaned_text": card.cleaned_text,
            "product": (
                getattr(result, "product", "")
                if result else
                existing.get("product", "")
            ),
            "display_name": (
                getattr(result, "display_name", "")
                if result else
                existing.get("display_name", "")
            ),
            "code": (
                getattr(result, "code", "")
                if result else
                existing.get("code", "")
            ),
            "material": card.material,
            "quantity": card.quantity,
            "brand": card.brand,
            "country": card.country,
            "specs": card.specs,
            "sections": card.sections,
            "features": card.features,
            "images": getattr(card, "images", []),
        }

        self.mark_dirty()

    def find(self, card):

        result = self.find_by_url(card.url)

        if result:
            return result

        if card.slug and len(card.slug) > 5:

            result = self.find_by_slug(card.slug)

            if result:
                return result

        return None

    def all(self):
        return self.data.values()

    def remove_without_code(self):

        self.data = {
            url: card
            for url, card in self.data.items()
            if card.get("code")
        }

        self.mark_dirty()
        self.flush()
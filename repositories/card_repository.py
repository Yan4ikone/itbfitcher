from utils.json_repository import JsonRepository


class CardRepository(JsonRepository):

    def __init__(self):
        super().__init__("learning/cards.json")

    def find_by_url(self, url):
        return self.data.get(url)

    def find_by_slug(self, slug):
        slug = (slug or "").lower()

        for item in self.data.values():

            if item.get("slug", "").lower() == slug:
                return item

        return None

    def remember(self, card, result):
        self.data[card.url] = {

            "url": card.url,
            "slug": card.slug,
            "title": card.title,
            "description": card.description,
            "cleaned_text": card.cleaned_text,

            "product": result.product,
            "display_name": result.dropdown,
            "code": result.code,

            "material": getattr(card, "material", ""),
            "quantity": getattr(card, "quantity", ""),
            "brand": getattr(card, "brand", ""),
            "country": getattr(card, "country", ""),

            "specs": getattr(card, "specs", {}),
            "sections": getattr(card, "sections", {}),
            "features": getattr(card, "features", {})
        }
        self.mark_dirty()
        self.flush()

    def find(self, card):

        result = self.find_by_url(card.url)

        if result:
            return result

        return self.find_by_slug(card.slug)

    def all(self):
        return self.data.values()
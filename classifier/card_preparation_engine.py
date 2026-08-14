from classifier.product_candidates import ProductCandidates
from cleaner.product_cleaner import clean_text
from cleaner.product_extractor import ProductExtractor
from classifier.normalizer import normalize_name


class CardPreparationEngine:

    def __init__(self):

        self.extractor = ProductExtractor()

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def prepare(self, card):

        self._prepare_title(card)
        self._prepare_description(card)
        self._prepare_slug(card)
        self.candidates = ProductCandidates()
        self.candidates.build(card)

        return card

    # ==========================================================
    # TITLE
    # ==========================================================

    def _prepare_title(self, card):

        text = card.title or ""
        cleaned, removed, replaced = clean_text(text)
        card.clean_title = normalize_name(cleaned)
        card.normalizer_log.append({
            "source": "TITLE",
            "removed": removed,
            "replaced": replaced,
            "result": card.clean_title
        })

    # ==========================================================
    # DESCRIPTION
    # ==========================================================

    def _prepare_description(self, card):

        text = card.description or ""
        cleaned, removed, replaced = clean_text(text)
        card.clean_description = normalize_name(cleaned)
        card.normalizer_log.append({
            "source": "DESCRIPTION",
            "removed": removed,
            "replaced": replaced,
            "result": card.clean_description
        })

    # ==========================================================
    # URL
    # ==========================================================

    def _prepare_slug(self, card):

        cleaned, removed, replaced = clean_text(
            card.url_product_name
        )
        card.clean_slug = normalize_name(cleaned)
        card.normalizer_log.append({
            "source": "URL",
            "removed": removed,
            "replaced": replaced,
            "result": card.clean_slug
        })


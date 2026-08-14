from datetime import datetime
from pathlib import Path


class DecisionLogger:

    def __init__(self):

        self.folder = Path("logs")
        self.folder.mkdir(exist_ok=True)
    # ==========================================================
    # PUBLIC
    # ==========================================================
    def save(self, card, result):

        filename = (
            datetime.now()
            .strftime("%Y-%m-%d")
            + ".log"
        )
        path = self.folder / filename

        with open(path, "a", encoding="utf-8") as f:

            self._write_header(f, card, result)
            self._write_candidates(f, result)
            f.write("\n")
            f.write("=" * 100)
            f.write("\n\n")
    # ==========================================================
    # HEADER
    # ==========================================================
    def _write_header(self, f, card, result):

        f.write("=" * 100)
        f.write("\n")
        f.write(f"URL: {card.url}\n")
        f.write(f"TITLE: {card.title}\n")

        if getattr(card, "slug", ""):
            f.write(f"SLUG: {card.slug}\n")

        if getattr(card, "cleaned_text", ""):
            f.write(f"CLEANED: {card.cleaned_text}\n")
        f.write("\n")
        f.write(f"RESULT PRODUCT : {result.product}\n")
        f.write(f"RESULT CODE    : {result.code}\n")
        f.write(f"SOURCE         : {result.source}\n")
        f.write(f"CONFIDENCE     : {result.confidence}\n")

        if result.material:
            f.write(f"MATERIAL       : {result.material}\n")
        f.write("\n")
    # ==========================================================
    # CANDIDATES
    # ==========================================================
    def _write_candidates(self, f, result):

        if not result.product_scores:

            f.write("NO CANDIDATES\n")
            return

        f.write("CANDIDATES\n")
        f.write("-" * 100)
        f.write("\n")

        for index, candidate in enumerate(result.product_scores, start=1):

            self._write_candidate(f, index, candidate)
    # ==========================================================
    # ONE CANDIDATE
    # ==========================================================
    def _write_candidate(self, f, index, candidate):

        f.write("\n")
        f.write(f"{index}. {candidate.product}\n")
        f.write(f"Score : {candidate.score}\n")
        f.write(f"Code  : {candidate.code}\n")

        if candidate.material:
            f.write(f"Material : {candidate.material}\n")
        if candidate.material_code:
            f.write(
                f"Material code : "
                f"{candidate.material_code}\n"
            )
        f.write("\n")
        f.write("BREAKDOWN\n")
        if candidate.breakdown:
            for key, value in sorted(
                    candidate.breakdown.items(),
                    key=lambda x: x[1],
                    reverse=True,
            ):
                f.write(f"    {key:<20} {value}\n")
        f.write("\n")
        f.write("MATCHES\n")
        if not candidate.matches:
            f.write("    -\n")
        else:
            for match in sorted(
                    candidate.matches,
                    key=lambda x: x["points"],
                    reverse=True,
            ):
                f.write(
                    f"    "
                    f"+{match['points']:>4} "
                    f"{match['type']:<20}"
                    f"{match['text']}\n"
                )
        f.write("\n")
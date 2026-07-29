class ResolverDebugger:

    def __init__(self, enabled=True):

        self.enabled = enabled

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def print(self, card, parsed, candidates):

        if not self.enabled:
            return

        print()
        print("=" * 80)
        print("PRODUCT RESOLVER")
        print("=" * 80)
        print()
        print("TITLE")
        print(card.title)

        if parsed.get("cleaned_text"):
            print()
            print("CLEANED")
            print(parsed["cleaned_text"])

        if parsed.get("product_name"):
            print()
            print("EXTRACTED")
            print(parsed["product_name"])
        print()
        print("-" * 80)

        if not candidates:

            print("NO CANDIDATES")
            print("=" * 80)
            return

        for index, candidate in enumerate(candidates[:10], start=1):
            self._print_candidate(index, candidate)
        print("=" * 80)

    # ==========================================================
    # CANDIDATE
    # ==========================================================

    def _print_candidate(self, index, candidate):

        print()
        print(f"{index}. {candidate.product}")
        print(f"Score      : {candidate.score}")
        print(f"Code       : {candidate.code}")

        if candidate.material:

            print(f"Material   : {candidate.material}")

        if candidate.material_code:

            print(f"Mat. code  : {candidate.material_code}")
        print()
        print("BREAKDOWN")

        if candidate.breakdown:

            width = max(len(key)
                for key in candidate.breakdown
            )
            for key, value in sorted(
                    candidate.breakdown.items(),
                    key=lambda x: x[1],
                    reverse=True,
            ):
                print(f"  {key:<{width}} : {value}")
        print()
        print("MATCHES")

        if not candidate.matches:

            print("  -")

        else:

            for item in sorted(
                    candidate.matches,
                    key=lambda x: x["points"],
                    reverse=True,
            ):
                print(
                    f"  +{item['points']:>4} "
                    f"{item['type']:<20}"
                    f"{item['text']}"
                )
        print("-" * 80)
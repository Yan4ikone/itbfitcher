class CodeResolver:

    def __init__(self, result):
        self.result = result

    def apply(self, code, source, confidence, reason):

        if not code:
            return

        self.result.code = str(code)
        self.result.source = source
        self.result.confidence = confidence

        self.result.trace.add(
            "CODE",
            f"{source}: {code} ({reason})"
        )
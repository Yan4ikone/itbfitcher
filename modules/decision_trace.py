class DecisionTrace:

    def __init__(self):

        self.steps = []

    def add(self, stage: str, message: str):

        self.steps.append({
            "stage": stage,
            "message": message
        })

    def clear(self):

        self.steps.clear()

    def to_text(self):

        if not self.steps:
            return ""

        lines = []

        for step in self.steps:

            lines.append(
                f"[{step['stage']}] {step['message']}"
            )

        return "\n".join(lines)
class LearningClassifier:

    def __init__(self, knowledge):
        self.knowledge = knowledge

    def apply(self, result):

        if result.product:

            if not self.knowledge.has_product(result.product):
                result.new_product = True
                result.trace.add("LEARNING", f"Товар '{result.product}' отсутствует в PRODUCTS")

            return result

        if result.dropdown:

            dropdown = self.knowledge.find_dropdown(result.dropdown)

            if not dropdown:

                result.new_dropdown = True
                result.trace.add("LEARNING", f"'{result.dropdown}' отсутствует в DROPDOWN")

        return result
from utils.json_repository import JsonRepository


class StatisticsRepository(JsonRepository):

    def __init__(self):
        super().__init__("learning/statistics.json")

    def update(self, result):

        if not result.product:
            return

        stat = self.data.setdefault(
            result.product,
            {
                "hits": 0,
                "codes": {},
                "materials": {}
            }
        )

        stat["hits"] += 1

        if result.code:
            stat["codes"][result.code] = (
                stat["codes"].get(result.code, 0) + 1
            )

        if result.material:
            stat["materials"][result.material] = (
                stat["materials"].get(result.material, 0) + 1
            )

        self.mark_dirty()

    def get(self, product):
        return self.data.get(product)

    def all(self):
        return self.data.items()
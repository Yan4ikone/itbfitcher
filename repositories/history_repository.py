from utils.json_repository import JsonRepository


class HistoryRepository(JsonRepository):

    def __init__(self):
        super().__init__("learning/learning_history.json")

    def all(self):
        return self.data.items()

    def get(self, name):
        return self.data.get(name)

    def set(self, name, value):
        self.data[name] = value



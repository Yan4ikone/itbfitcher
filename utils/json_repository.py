import json
from pathlib import Path


class JsonRepository:

    def __init__(self, file_path):
        self.file = Path(file_path)
        self.file.parent.mkdir(parents=True, exist_ok=True)

        self.data = self._load()
        self._dirty = False

    def _load(self):
        if not self.file.exists():
            return {}

        try:
            with open(self.file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save(self):
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(
                self.data,
                f,
                ensure_ascii=False,
                indent=4
            )

    def mark_dirty(self):
        self._dirty = True

    def flush(self):
        if self._dirty:
            self.save()
            self._dirty = False
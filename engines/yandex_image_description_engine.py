import base64
import io
import os

import requests


class YandexImageDescriptionEngine:
    """
    Описывает изображение по фото через Yandex AI Studio (Foundation
    Models, мультимодальная модель Qwen). Интерфейс совпадает с
    ImageDescriptionEngine (Anthropic) - describe(image) -> str, где
    image - уже загруженный PIL.Image. CardImageProcessor сам грузит
    картинку по URL через ImageLoader ДО вызова describe() (см.
    processors/card_image_processor.py) - здесь её НЕ перезагружаем
    повторно по сети (в присланном черновике describe() принимал
    URL и качал картинку сам - оставлять так не стал, это был бы
    двойной запрос за одной и той же картинкой и другой интерфейс,
    несовместимый с ImageDescriptionService/CardImageProcessor без
    их правки).

    Требует переменные окружения YC_API_KEY и YC_FOLDER_ID (ключ и
    ID каталога Yandex Cloud) - не хранятся в коде.

    Выбирается через переменную окружения IMAGE_ENGINE=yandex (см.
    engines/decision_engine.py::_create_image_engine) - по умолчанию
    используется Anthropic (engines/image_description_engine.py),
    чтобы можно было сравнить оба варианта, не меняя код.
    """

    API_URL = "https://ai.api.cloud.yandex.net/v1/responses"

    def __init__(self):

        print("IMAGE ENGINE INIT (Yandex AI Studio)")

        self.api_key = os.getenv("YC_API_KEY")
        self.folder_id = os.getenv("YC_FOLDER_ID")

        if not self.api_key or not self.folder_id:
            raise ValueError(
                "YC_API_KEY и YC_FOLDER_ID должны быть заданы "
                "переменными окружения"
            )

        # Мультимодальная модель Qwen с поддержкой изображений
        # (Base64) - см. документацию Yandex AI Studio.
        self.model = "qwen3-235b-a22b-fp8"
        self.timeout = 30

        self.prompt = (
            "Опиши товар на изображении. "
            "Игнорируй фон. "
            "Укажи только полезные характеристики: "
            "тип изделия, материал, форму, "
            "цвет, назначение. "
            "Отвечай кратко, списком, без заголовков."
        )

    def describe(self, image):

        try:
            image_base64 = self._encode_image(image)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {self.api_key}",
                "x-folder-id": self.folder_id,
            }

            payload = {
                "model": f"gpt://{self.folder_id}/{self.model}",
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": self.prompt,
                            },
                            {
                                "type": "input_image",
                                "image_url": (
                                    "data:image/jpeg;base64,"
                                    + image_base64
                                ),
                                "detail": "auto",
                            },
                        ],
                    }
                ],
            }

            response = requests.post(
                self.API_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()

            return self._extract_text(response.json())

        except requests.exceptions.Timeout:
            print("IMAGE TIMEOUT (Yandex)")
            return ""

        except requests.exceptions.ConnectionError:
            print("YANDEX СЕТЬ НЕДОСТУПНА")
            return ""

        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:500]
            except Exception:
                pass
            print(f"YANDEX API ERROR: {e} {body}")
            return ""

        except Exception as e:
            print(f"IMAGE ERROR (Yandex): {e}")
            return ""

    def _encode_image(self, image):

        if image.mode != "RGB":
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)

        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _extract_text(self, data):
        # Документация Yandex AI Studio описывает удобное свойство
        # response.output_text - но, судя по всему (по аналогии с
        # OpenAI Responses API, на которую эта схема похожа), это
        # готовое свойство ИХ SDK, а не гарантированный ключ в сыром
        # JSON-ответе (мы бьём в REST напрямую через requests, без
        # их SDK). Проверяем оба пути: сначала верхнеуровневый ключ
        # (вдруг он всё-таки есть), если пусто - собираем текст из
        # output[].content[].text (задокументированная структура
        # ответа Responses API).
        #
        # ВАЖНО: data.get("output", []) padает с "'NoneType' object is
        # not iterable", если ключ "output" в ответе ЕСТЬ, но его
        # значение - JSON null (а не просто отсутствует) - именно это
        # реально происходило на живом прогоне (см. лог "IMAGE ERROR
        # (Yandex): 'NoneType' object is not iterable"). .get(key, def)
        # подставляет default ТОЛЬКО когда ключа нет вообще, а не когда
        # он есть и равен null - нужно "or []" на каждом уровне.
        text = (data.get("output_text") or "").strip()
        if text:
            return text

        chunks = []
        for item in (data.get("output") or []):
            for block in (item.get("content") or []):
                if block.get("type") == "output_text":
                    value = block.get("text", "")
                    if value:
                        chunks.append(value)

        result = " ".join(chunks).strip()

        if not result:
            # Ничего не удалось извлечь - печатаем status/error (если
            # они есть в ответе), чтобы в логе было видно ПОЧЕМУ, а не
            # только то, что описание пустое. Частая причина - модель
            # ещё не готова (status="in_progress") или запрос упал на
            # стороне Yandex (status="failed"/"error" в ответе).
            status = data.get("status")
            error = data.get("error")
            if status or error:
                print(
                    "YANDEX EMPTY OUTPUT: status=",
                    status,
                    "error=",
                    error,
                )

        return result

import base64
import io

import requests


class ImageDescriptionEngine:

    def __init__(self):

        print("IMAGE ENGINE INIT")
        self.url = ("http://127.0.0.1:11434/api/generate")
        self.model = "qwen2.5vl:3b"
        self.timeout = 15


    def describe(self, image):
        try:
            image_base64 = self._encode_image(image)
            response = requests.post(
                self.url,
                json={
                    "model": self.model,
                    "prompt": (
                        "Опиши товар на изображении. "
                        "Игнорируй фон. "
                        "Укажи только полезные характеристики: "
                        "тип изделия, материал, форму, "
                        "цвет, назначение."
                    ),
                    "images": [image_base64],
                    "stream": False
                },
                timeout=self.timeout
            )
            if response.status_code != 200:
                print("OLLAMA ERROR:", response.status_code)

                return ""

            data = response.json()

            return data.get(
                "response",
                ""
            ).strip()

        except requests.Timeout:

            print("IMAGE TIMEOUT")

            return ""


        except requests.ConnectionError:
            print("OLLAMA OFFLINE")
            return ""


        except Exception as e:
            print("IMAGE ERROR:", e)
            return ""


    def _encode_image(self, image):

        if image.mode != "RGB":
            image = image.convert("RGB")
        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=85
        )
        return base64.b64encode(
            buffer.getvalue()
        ).decode("utf-8")
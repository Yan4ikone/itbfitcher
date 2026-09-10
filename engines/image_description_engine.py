import base64
import io
import os

import anthropic


class ImageDescriptionEngine:
    """
    Раньше стучался в локальный Ollama (qwen2.5vl:3b на 127.0.0.1) -
    требует GPU на машине куратора. Теперь - внешний запрос к
    Anthropic API. Внешний интерфейс (describe(image) -> str) не
    изменился, поэтому ImageDescriptionService/CardImageProcessor
    трогать не нужно.

    Требует переменную окружения ANTHROPIC_API_KEY (см. ниже, как
    её задать) - ключ НЕ хранится в коде.
    """

    def __init__(self):

        print("IMAGE ENGINE INIT (Anthropic API)")

        # Ключ берётся из переменной окружения ANTHROPIC_API_KEY -
        # client сам её найдёт, явно передавать не нужно.
        self.client = anthropic.Anthropic()

        # haiku - самая быстрая и дешёвая модель с поддержкой
        # изображений. Для сотен карточек за прогон это обычно
        # важнее, чем предельное качество описания - если результат
        # окажется недостаточно точным, замените на "claude-sonnet-5".
        self.model = "claude-haiku-4-5-20251001"
        self.max_tokens = 300

        self.prompt = (
            "Опиши товар на изображении. "
            "Игнорируй фон. "
            "Укажи только полезные характеристики: "
            "тип изделия, материал, форму, "
            "цвет, назначение."
        )

    def describe(self, image):

        try:
            image_base64, media_type = self._encode_image(image)

            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": self.prompt,
                            },
                        ],
                    }
                ],
            )

            return "".join(
                block.text
                for block in response.content
                if block.type == "text"
            ).strip()

        except anthropic.APITimeoutError:
            print("IMAGE TIMEOUT")
            return ""

        except anthropic.APIConnectionError:
            print("ANTHROPIC СЕТЬ НЕДОСТУПНА")
            return ""

        except anthropic.RateLimitError:
            print("ANTHROPIC RATE LIMIT")
            return ""

        except anthropic.APIStatusError as e:
            print("ANTHROPIC ERROR:", e.status_code, e.message)
            return ""

        except Exception as e:
            print("IMAGE ERROR:", e)
            return ""

    def _encode_image(self, image):

        if image.mode != "RGB":
            image = image.convert("RGB")

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)

        return (
            base64.b64encode(buffer.getvalue()).decode("utf-8"),
            "image/jpeg",
        )

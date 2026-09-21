import base64
import io
import logging
import os

import requests

log = logging.getLogger(__name__)


class QwenImageDescriptionEngine:
    """
    Описывает изображение через Alibaba Cloud DashScope (модель
    Qwen-VL-Max, международный контур). Интерфейс совпадает с
    ImageDescriptionEngine (Anthropic) и YandexImageDescriptionEngine -
    describe(image) -> str, где image - уже загруженный PIL.Image.
    CardImageProcessor сам грузит картинку по URL через ImageLoader ДО
    вызова describe() (см. processors/card_image_processor.py) -
    здесь её НЕ перезагружаем повторно по сети.

    Требует переменные окружения QWEN_API_KEY (ключ Alibaba Cloud
    Model Studio, созданный ИМЕННО в международной консоли - регион
    Singapore/ap-southeast-1, а не в материковой китайской) и
    QWEN_WORKSPACE_ID (id вашего workspace, вида "ws-..." - виден в
    консоли рядом с ключом). Ни то, ни другое не хранится в коде.

    Выбирается через переменную окружения IMAGE_ENGINE=qwen (см.
    engines/decision_engine.py::_create_image_engine) - по умолчанию
    используется Anthropic (engines/image_description_engine.py),
    чтобы можно было сравнить все варианты, не меняя код.

    ВАЖНО про адрес API: раньше здесь стоял общий домен
    dashscope-intl.aliyuncs.com (международный контур, НЕ материковый
    китайский dashscope.aliyuncs.com - у них разные ключи/аккаунты).
    Alibaba Cloud теперь выдаёт КАЖДОМУ workspace свой отдельный
    ("dedicated") домен вида
    https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com - общий
    домен официально всё ещё "остаётся доступен" как legacy-вариант,
    но при создании ключа явно показывается именно выделенный домен
    конкретного workspace, поэтому используем его.
    """

    API_HOST_TEMPLATE = (
        "https://{workspace_id}.ap-southeast-1.maas.aliyuncs.com"
        "/compatible-mode/v1/chat/completions"
    )

    def __init__(self):

        print("IMAGE ENGINE INIT (Qwen-VL via DashScope)")

        self.api_key = os.getenv("QWEN_API_KEY")
        self.workspace_id = os.getenv("QWEN_WORKSPACE_ID")

        if not self.api_key:
            raise ValueError(
                "Переменная окружения QWEN_API_KEY должна быть задана"
            )

        if not self.workspace_id:
            raise ValueError(
                "Переменная окружения QWEN_WORKSPACE_ID должна быть "
                "задана (id workspace вида 'ws-...', виден в консоли "
                "Model Studio рядом с API-ключом)"
            )

        self.api_url = self.API_HOST_TEMPLATE.format(
            workspace_id=self.workspace_id,
        )

        # Флагманская мультимодальная модель DashScope.
        # Альтернатива (дешевле/новее): "qwen2.5-vl-72b-instruct".
        self.model = "qwen-vl-max"
        self.timeout = 30

        self.prompt = (
            "Ты - эксперт по классификации и описанию товаров. "
            "Внимательно изучи изображение. Игнорируй фон и "
            "посторонние предметы. "
            "Опиши товар СТРОГО по следующим пунктам (без вступлений "
            "и лишних слов):\n"
            "- Тип: [что это за изделие]\n"
            "- Материал: [основной видимый материал]\n"
            "- Цвет: [основной цвет]\n"
            "- Форма/Детали: [ключевые визуальные особенности, "
            "фурнитура, узоры]\n"
            "- Назначение: [для чего используется, исходя из вида]"
        )

    def describe(self, image):

        try:
            image_base64 = self._encode_image(image)

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

            # Формат OpenAI Chat Completions (поддерживается DashScope
            # через compatible-mode).
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": self.prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": (
                                        "data:image/jpeg;base64,"
                                        + image_base64
                                    ),
                                },
                            },
                        ],
                    }
                ],
                # Низкая температура - для строгих, фактологических
                # ответов, не творческих.
                "temperature": 0.1,
            }

            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()

            return self._extract_text(response.json())

        except requests.exceptions.Timeout:
            print("IMAGE TIMEOUT (Qwen)")
            log.warning("IMAGE TIMEOUT (Qwen)")
            return ""

        except requests.exceptions.RequestException as e:
            body = ""
            try:
                body = e.response.text[:500]
            except Exception:
                pass
            print(f"QWEN API ERROR: {e} | Body: {body}")
            log.error("QWEN API ERROR: %s | Body: %s", e, body)
            return ""

        except Exception as e:
            print(f"IMAGE ERROR (Qwen): {e}")
            log.exception("IMAGE ERROR (Qwen)")
            return ""

    def _encode_image(self, image):

        if image.mode != "RGB":
            image = image.convert("RGB")

        # Слишком маленькая картинка - модель не увидит деталей.
        # Минимальный апскейл до 512px по меньшей стороне.
        min_side = min(image.size)

        if min_side < 512:
            from PIL import Image

            scale = 512 / min_side
            new_size = (
                int(image.width * scale),
                int(image.height * scale),
            )
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)

        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _extract_text(self, data):
        # Стандартный разбор ответа OpenAI-совместимого API.
        try:
            choices = data.get("choices") or []

            if not choices:
                print(
                    "QWEN EMPTY OUTPUT: нет choices в ответе, "
                    f"raw={str(data)[:300]}"
                )
                log.warning(
                    "QWEN EMPTY OUTPUT: нет choices в ответе, raw=%s",
                    str(data)[:300],
                )
                return ""

            message = choices[0].get("message") or {}
            text = (message.get("content") or "").strip()

            return text

        except Exception as e:
            print(
                f"QWEN PARSE ERROR: {e}, "
                f"raw data: {str(data)[:200]}"
            )
            log.exception(
                "QWEN PARSE ERROR, raw data: %s",
                str(data)[:200],
            )
            return ""

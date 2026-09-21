import base64
import io
import logging
import os

import requests

log = logging.getLogger(__name__)


class TimewebImageDescriptionEngine:
    """
    Описывает изображение через AI Gateway Timeweb Cloud - единый
    OpenAI-совместимый API-шлюз, который проксирует запросы к разным
    провайдерам (в т.ч. Anthropic Claude) с оплатой в рублях, без
    блокировок по IP/картам, характерных для прямого обращения к
    api.anthropic.com из РФ. Интерфейс совпадает с
    ImageDescriptionEngine (Anthropic), YandexImageDescriptionEngine и
    QwenImageDescriptionEngine - describe(image) -> str, где image -
    уже загруженный PIL.Image. CardImageProcessor сам грузит картинку
    по URL через ImageLoader ДО вызова describe() (см.
    processors/card_image_processor.py) - здесь её НЕ перезагружаем
    повторно по сети.

    Требует переменную окружения TIMEWEB_AI_API_KEY (ключ из личного
    кабинета Timeweb Cloud -> AI Gateway) - не хранится в коде.
    Опционально TIMEWEB_AI_MODEL - переопределить модель по умолчанию
    (см. self.model ниже), если понадобится другая версия Claude или
    вообще другой провайдер через тот же шлюз.

    Выбирается через переменную окружения IMAGE_ENGINE=timeweb (см.
    engines/decision_engine.py::_create_image_engine) - по умолчанию
    используется Anthropic напрямую (engines/image_description_engine.py),
    чтобы можно было сравнить варианты, не меняя код.

    ВАЖНО: формат запроса - стандартный OpenAI Chat Completions
    (client = OpenAI(base_url="https://api.timeweb.ai/v1", ...) в
    примерах Timeweb), поэтому бьём напрямую по REST (requests), как и
    в QwenImageDescriptionEngine, без зависимости от пакета openai.
    Передача изображения - через content-блок image_url с data-URL
    (base64) - это тот же стандартный формат, что уже подтверждённо
    работает у Qwen/DashScope через тот же compatible-mode; официальная
    документация AI Gateway на момент написания не описывает этот
    случай явно (только текстовые примеры) - если картинка не будет
    восприниматься, первое, что проверить - именно этот момент.
    """

    API_URL = "https://api.timeweb.ai/v1/chat/completions"

    def __init__(self):

        print("IMAGE ENGINE INIT (Timeweb AI Gateway)")

        self.api_key = os.getenv("TIMEWEB_AI_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Переменная окружения TIMEWEB_AI_API_KEY должна быть "
                "задана (ключ из личного кабинета Timeweb Cloud -> "
                "AI Gateway)"
            )

        # Claude Haiku через шлюз - имя модели с префиксом провайдера,
        # как в примерах Timeweb ("anthropic/<модель>"). Если качество
        # описаний окажется недостаточным, замените на
        # "anthropic/claude-sonnet-5" через TIMEWEB_AI_MODEL.
        self.model = os.getenv(
            "TIMEWEB_AI_MODEL", "anthropic/claude-haiku-4-5"
        )
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
                "Authorization": f"Bearer {self.api_key}",
            }

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
                self.API_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()

            return self._extract_text(response.json())

        except requests.exceptions.Timeout:
            print("IMAGE TIMEOUT (Timeweb)")
            log.warning("IMAGE TIMEOUT (Timeweb)")
            return ""

        except requests.exceptions.RequestException as e:
            body = ""
            try:
                body = e.response.text[:500]
            except Exception:
                pass
            print(f"TIMEWEB API ERROR: {e} | Body: {body}")
            # ДОБАВЛЕНО: дублируем в файл (logs/errors_YYYY-MM-DD.log,
            # см. utils/app_logging.py) - print() выше не виден в
            # windowed-сборке и/или в дочернем процессе
            # classifier-пула (см. processors/ozon_auto_processor.py::
            # _init_classifier_worker) - именно там реально вызывается
            # describe() для карточек без кода.
            log.error("TIMEWEB API ERROR: %s | Body: %s", e, body)
            return ""

        except Exception as e:
            print(f"IMAGE ERROR (Timeweb): {e}")
            log.exception("IMAGE ERROR (Timeweb)")
            return ""

    def _encode_image(self, image):

        if image.mode != "RGB":
            image = image.convert("RGB")

        # Слишком маленькая картинка - модель не увидит деталей.
        # Минимальный апскейл до 512px по меньшей стороне (см. такое
        # же решение в QwenImageDescriptionEngine).
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
        # Стандартный разбор ответа OpenAI Chat Completions.
        try:
            choices = data.get("choices") or []

            if not choices:
                print(
                    "TIMEWEB EMPTY OUTPUT: нет choices в ответе, "
                    f"raw={str(data)[:300]}"
                )
                log.warning(
                    "TIMEWEB EMPTY OUTPUT: нет choices в ответе, raw=%s",
                    str(data)[:300],
                )
                return ""

            message = choices[0].get("message") or {}
            text = (message.get("content") or "").strip()

            return text

        except Exception as e:
            print(
                f"TIMEWEB PARSE ERROR: {e}, "
                f"raw data: {str(data)[:200]}"
            )
            log.exception(
                "TIMEWEB PARSE ERROR, raw data: %s",
                str(data)[:200],
            )
            return ""

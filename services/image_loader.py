from PIL import Image
from io import BytesIO
import requests


class ImageLoader:


    def __init__(self):
        self.timeout = 10

    def load_from_url(self, url):
        try:
            response = requests.get(
                url,
                timeout=self.timeout,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))

            return image.convert("RGB")
        except Exception as e:
            print(f"IMAGE LOAD ERROR: {e}")
            return None
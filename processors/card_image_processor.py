from services.image_loader import ImageLoader


class CardImageProcessor:


    def __init__(self, image_service):
        self.image_service = image_service
        self.image_loader = ImageLoader()



    def process(self, card):
        if not card.images:
            return card
        try:

            image = self.image_loader.load_from_url(
                card.images[0]
            )
            if image is None:
                return card


            description = (
                self.image_service.describe_images(
                    [image]
                )
            )
            if description:
                card.image_description = description
                if card.cleaned_text:
                    card.cleaned_text += (
                        " "
                        + description
                    )
                else:
                    card.cleaned_text = description
        except Exception as e:
            print(f"IMAGE PROCESS ERROR: {e}")

        return card
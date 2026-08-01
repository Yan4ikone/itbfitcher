class ImageDescriptionService:


    def __init__(self, engine):
        self.engine = engine



    def describe_images(self, images):

        if not images:
            return ""

        for image in images:
            result = self.engine.describe(image)
            if result:
                return result
        return ""
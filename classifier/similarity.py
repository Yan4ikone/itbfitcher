from classifier.similarity_engine import (find_similar_products, extract_features)
from modules.feature_predictor import predict_features
from engines.material_engine import choose_by_material


class SimilarityClassifier:

    def __init__(self, learning_history):
        self.learning_history = learning_history

    def find(self, card):

        similar = find_similar_products(card, self.learning_history)
        features = extract_features(card)
        predicted = predict_features(similar,features)
        material = choose_by_material(similar, card)

        return similar, predicted, material
from collections import Counter


def predict_features(similar_products, current_features):

    predicted = dict(current_features)

    counters = {}

    for product in similar_products:

        features = product.features or {}

        for feature_name, value in features.items():

            if feature_name in predicted:
                continue

            if feature_name not in counters:
                counters[feature_name] = Counter()

            counters[feature_name][value] += product.count

    for feature_name, counter in counters.items():

        if not counter:
            continue

        value, amount = counter.most_common(1)[0]

        if amount >= 3:
            predicted[feature_name] = value

    return predicted
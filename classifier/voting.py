from collections import Counter


class VotingEngine:

    def vote(self, similar, predicted):

        counter = Counter()

        for item in similar:

            weight = item["count"]

            item_features = item.get(
                "features",
                {}
            )

            for key, value in predicted.items():

                if item_features.get(key) == value:
                    weight += 5

            counter[item["code"]] += weight

        if not counter:
            return None, 0, counter

        code, amount = counter.most_common(1)[0]

        return code, amount, counter
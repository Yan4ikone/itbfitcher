import re


def _safe(text):
    return (text or "").lower()

def score_products(card, knowledge):

    candidates = []
    title = _safe(card.title)
    excel_title = _safe(getattr(card, "excel_title", ""))

    if excel_title:
        title += (
                " " + excel_title
                + " " + excel_title
                + " " + excel_title
        )
    BAD_DESCRIPTION = (
        "мы сосредоточены",
        "российским потребителям",
        "трансграничной электронной коммерции",
        "каждая ваша покупка",
        "завоевать доверие",
        "распродажа"
    )

    description = _safe(getattr(card, "description", ""))

    for bad in BAD_DESCRIPTION:
        if bad in description:
            description = ""
            break
    raw_text = _safe(getattr(card, "raw_text", ""))
    slug = _safe(getattr(card, "slug", ""))
    specs = getattr(card, "specs", {}) or {}
    specs_text = " ".join(_safe(str(v))
        for v in specs.values()
    )

    for product_name, info in knowledge.all_products():

        score = 0
        matches = []
        title_score = 0
        desc_score = 0
        slug_score = 0
        spec_score = 0
        raw_score = 0
        pname = product_name.lower()

        if pname in slug:
            score += 220
            matches.append({
                "type": "SLUG",
                "text": pname,
                "points": 220
            })

        if pname in title:
            title_score += 300
            matches.append({
                "type": "TITLE",
                "text": pname,
                "points": 300
            })

        for alias in info.get("aliases", []):

            alias_l = alias.lower()

            if alias_l in description:
                desc_score += 1000
                matches.append({
                    "type": "DESC_ALIAS",
                    "text": alias,
                    "points": 1000
                })

            elif alias_l in title:
                score += 400
                matches.append({
                    "type": "TITLE_ALIAS",
                    "text": alias,
                    "points": 400
                })

            elif alias_l in slug:
                slug_score += 220
                matches.append({
                    "type": "SLUG_ALIAS",
                    "text": alias,
                    "points": 220
                })

        for pattern in info.get("patterns", []):
            try:
                if re.search(pattern, title):
                    score += 350
                    matches.append({
                        "type": "TITLE_PATTERN",
                        "text": pattern,
                        "points": 350
                    })

                elif re.search(pattern, description):
                    score += 800
                    matches.append({
                        "type": "DESC_PATTERN",
                        "text": pattern,
                        "points": 800
                    })

                elif re.search(pattern, specs_text):
                    spec_score += 150
                    matches.append({
                        "type": "SPEC_PATTERN",
                        "text": pattern,
                        "points": 150
                    })

            except re.error:
                continue

        for word in info.get("score_words", []):
            word_l = word.lower()

            if word_l in title:
                score += 40
                matches.append({
                    "type": "TITLE_WORD",
                    "text": word,
                    "points": 40
                })

            elif word_l in description:
                score += 500
                matches.append({
                    "type": "DESC_WORD",
                    "text": word,
                    "points": 500
                })

            elif word_l in specs_text:
                score += 50
                matches.append({
                    "type": "SPEC_WORD",
                    "text": word,
                    "points": 50
                })

        if pname in raw_text:
            raw_score += 30
            matches.append({
                "type": "RAW",
                "text": pname,
                "points": 30
            })

        score = (
                title_score
                + desc_score
                + slug_score
                + spec_score
                + raw_score
        )
        # Нет совпадений в названии и slug — сильный штраф
        if title_score == 0 and slug_score == 0:
            score -= 500

        # Совпадение только по описанию — подозрительно
        if desc_score > 0 and title_score == 0:
            score -= 300

        # Только RAW вообще не считаем
        if raw_score > 0 and title_score == 0 and slug_score == 0:
            score -= raw_score

        # Только score_words из описания — режем
        if desc_score > 1500 and title_score < 100:
            score //= 4

        if score > 0:
            candidates.append({
                "product": product_name,
                "score": score,
                "matches": matches,
                "breakdown": {
                    "TITLE": sum(x["points"] for x in matches if x["type"] == "TITLE"),
                    "TITLE_ALIAS": sum(x["points"] for x in matches if x["type"] == "TITLE_ALIAS"),
                    "DESC_ALIAS": sum(x["points"] for x in matches if x["type"] == "DESC_ALIAS"),
                    "TITLE_PATTERN": sum(x["points"] for x in matches if x["type"] == "TITLE_PATTERN"),
                    "DESC_PATTERN": sum(x["points"] for x in matches if x["type"] == "DESC_PATTERN"),
                    "SPEC_PATTERN": sum(x["points"] for x in matches if x["type"] == "SPEC_PATTERN"),
                    "TITLE_WORD": sum(x["points"] for x in matches if x["type"] == "TITLE_WORD"),
                    "DESC_WORD": sum(x["points"] for x in matches if x["type"] == "DESC_WORD"),
                    "SPEC_WORD": sum(x["points"] for x in matches if x["type"] == "SPEC_WORD"),
                    "SLUG": sum(x["points"] for x in matches if x["type"] == "SLUG"),
                    "SLUG_ALIAS": sum(x["points"] for x in matches if x["type"] == "SLUG_ALIAS"),
                    "TITLE_SCORE": title_score,
                    "DESC_SCORE": desc_score,
                    "SLUG_SCORE": slug_score,
                    "SPEC_SCORE": spec_score,
                    "RAW_SCORE": raw_score,
                    "RAW": sum(x["points"] for x in matches if x["type"] == "RAW")
                }
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    if candidates:
        top = candidates[0]["score"]
        if top < 150:
            return []
    if len(candidates) > 1:
        diff = (
                candidates[0]["score"]
                - candidates[1]["score"]
        )

        candidates[0]["diff"] = diff

    return candidates
# plugins/news_signal/plugin.py — Streamlit removed
# render_ui() deleted. Business logic and scoring unchanged.

BULLISH_WORDS = [
    "surge", "rally", "growth", "approval", "breakout",
    "profit", "record", "bullish", "partnership", "beat"
]

BEARISH_WORDS = [
    "crash", "fraud", "lawsuit", "war", "recession",
    "decline", "miss", "bankrupt", "sanctions", "hack"
]


def manifest():
    return {
        "name":     "news_signal",
        "version":  "1.1",
        "provides": ["news.signal"],
        "requires": ["news.search"]
    }


def score_headline(title):
    title_lower   = title.lower()
    bullish_score = sum(1 for w in BULLISH_WORDS if w in title_lower)
    bearish_score = sum(1 for w in BEARISH_WORDS if w in title_lower)
    return bullish_score, bearish_score


def handle_request(request, context):
    query = request["payload"].get("query", "Bitcoin")

    try:
        news_result = context.request("news.search", {"query": query})
    except Exception as e:
        return {"status": "error", "message": f"news.search failed: {e}"}

    if news_result["status"] != "success":
        return news_result

    articles      = news_result["data"]
    bullish_total = 0
    bearish_total = 0
    scored        = []

    for article in articles:
        title = article.get("title", "")
        bull, bear = score_headline(title)
        bullish_total += bull
        bearish_total += bear
        scored.append({
            "title":         title,
            "source":        article.get("source", {}).get("name", "Unknown"),
            "bullish_score": bull,
            "bearish_score": bear,
        })

    if bullish_total > bearish_total:
        signal = "BULLISH"
    elif bearish_total > bullish_total:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"

    context.publish("news.signal_generated", {"query": query, "signal": signal})

    return {
        "status": "success",
        "data": {
            "signal":        signal,
            "bullish_total": bullish_total,
            "bearish_total": bearish_total,
            "articles":      scored,
        }
    }

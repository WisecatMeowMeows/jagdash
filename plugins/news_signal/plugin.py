import streamlit as st
import pandas as pd


BULLISH_WORDS = [
    "surge",
    "rally",
    "growth",
    "approval",
    "breakout",
    "profit",
    "record",
    "bullish",
    "partnership",
    "beat"
]

BEARISH_WORDS = [
    "crash",
    "fraud",
    "lawsuit",
    "war",
    "recession",
    "decline",
    "miss",
    "bankrupt",
    "sanctions",
    "hack"
]


def manifest():
    return {
        "name": "news_signal",
        "version": "1.0",
        "provides": [
            "news.signal"
        ],
        "requires": [
            "news.search"
        ]
    }


def score_headline(title):
    title_lower = title.lower()

    bullish_score = 0
    bearish_score = 0

    for word in BULLISH_WORDS:
        if word in title_lower:
            bullish_score += 1

    for word in BEARISH_WORDS:
        if word in title_lower:
            bearish_score += 1

    return bullish_score, bearish_score


def handle_request(request, context):
    query = request["payload"].get(
        "query",
        "Bitcoin"
    )

    news_result = context.request(
        "news.search",
        {
            "query": query
        }
    )

    articles = news_result["data"]

    bullish_total = 0
    bearish_total = 0

    scored_articles = []

    for article in articles:
        title = article["title"]

        bull, bear = score_headline(title)

        bullish_total += bull
        bearish_total += bear

        scored_articles.append({
            "title": title,
            "source": article["source"]["name"],
            "bullish_score": bull,
            "bearish_score": bear
        })

    if bullish_total > bearish_total:
        signal = "BULLISH"

    elif bearish_total > bullish_total:
        signal = "BEARISH"

    else:
        signal = "NEUTRAL"

    context.publish(
        "news.signal_generated",
        {
            "query": query,
            "signal": signal
        }
    )

    return {
        "status": "success",
        "data": {
            "signal": signal,
            "bullish_total": bullish_total,
            "bearish_total": bearish_total,
            "articles": scored_articles
        }
    }


def render_ui(context):
    st.subheader("News Signal Engine")

    query = st.text_input(
        "Asset / Topic",
        value="Bitcoin"
    )

    if st.button("Generate News Signal"):
        try:
            result = context.request(
                "news.signal",
                {
                    "query": query
                }
            )

            data = result["data"]

            st.metric(
                "Overall Signal",
                data["signal"]
            )

            col1, col2 = st.columns(2)

            with col1:
                st.metric(
                    "Bullish Score",
                    data["bullish_total"]
                )

            with col2:
                st.metric(
                    "Bearish Score",
                    data["bearish_total"]
                )

            df = pd.DataFrame(
                data["articles"]
            )

            st.dataframe(
                df,
                use_container_width=True
            )

        except Exception as e:
            st.error(
                f"Signal generation failed: {e}"
            )
import streamlit as st
import requests
import pandas as pd
from datetime import datetime


#NEWS_API_KEY = "ce889b2521a74e6c9c5e892b57653cc2"



def manifest():
    return {
        "name": "news_scanner",
        "version": "1.0",
        "provides": [
            "news.search"
        ],
        "requires": []
    }


#def fetch_news(query):

@st.cache_data(ttl=300)
def fetch_news(query, api_key):

    url = "https://newsapi.org/v2/everything"

    params = {
        "q": query,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 20,
        "apiKey": api_key
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    return data.get("articles", [])


def handle_request(request, context):
    query = request["payload"].get(
        "query",
        "Bitcoin"
    )

    api_key = context.get_api_key(
        "newsapi"
    )

    if not api_key:
        raise Exception(
            "NewsAPI key missing. Add it in config plugin."
        )

    articles = fetch_news(
        query,
        api_key
    )

    return {
        "status": "success",
        "data": articles
    }


def render_ui(context):
    st.subheader("News Scanner")

    watchlist = [
        "Bitcoin",
        "Ethereum",
        "Oil",
        "Federal Reserve",
        "China",
        "AI Stocks"
    ]

    selected_watch = st.selectbox(
        "Watchlist",
        watchlist
    )

    custom_query = st.text_input(
        "Custom Query (optional)"
    )

    query = custom_query if custom_query else selected_watch

    if st.button("Scan News"):
        try:
            result = context.request(
                "news.search",
                {
                    "query": query
                }
            )

            articles = result["data"]

            if not articles:
                st.warning("No articles found.")
                return

            rows = []

            for article in articles:
                rows.append({
                    "Source": article["source"]["name"],
                    "Title": article["title"],
                    "Published": article["publishedAt"],
                    "URL": article["url"]
                })

            if len(articles) > 0:
                context.publish(
                    "news.scan_completed",
                    {
                        "query": query,
                        "article_count": len(articles)
                    }
                )

            df = pd.DataFrame(rows)

            st.dataframe(
                df,
                use_container_width=True
            )

        except Exception as e:
            st.error(
                f"News scan failed: {e}"
            )

        source_filter = st.text_input(
           "Filter Source (optional)"
        )

        if source_filter:
            rows = [
                row for row in rows
                if source_filter.lower()
                in row["Source"].lower()
            ]
# plugins/news_scanner/plugin.py — Streamlit removed
# render_ui() deleted. Business logic unchanged.

import requests
import pandas as pd
from datetime import datetime


def manifest():
    return {
        "name": "news_scanner",
        "version": "1.1",
        "provides": ["news.search"],
        "requires": []
    }


def fetch_news(query, api_key):
    """
    Fetch news articles from NewsAPI.
    No caching here since FastAPI handles requests statelessly.
    Caching can be added at the route level in main.py if needed.
    """
    url = "https://newsapi.org/v2/everything"
    params = {
        "q":        query,
        "language": "en",
        "sortBy":   "publishedAt",
        "pageSize": 20,
        "apiKey":   api_key
    }
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("articles", [])


def handle_request(request, context):
    query   = request["payload"].get("query", "Bitcoin")
    api_key = context.get_api_key("newsapi")

    if not api_key:
        return {
            "status":  "error",
            "message": "NewsAPI key missing. Add it in config plugin or .env file."
        }

    try:
        articles = fetch_news(query, api_key)
    except Exception as e:
        return {"status": "error", "message": f"NewsAPI request failed: {e}"}

    return {"status": "success", "data": articles}

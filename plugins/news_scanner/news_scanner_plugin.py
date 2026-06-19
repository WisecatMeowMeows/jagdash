# plugins/news_scanner/plugin.py — Streamlit removed
# render_ui() deleted. Business logic unchanged.

import requests
import pandas as pd
from datetime import datetime
from fastapi import Request, Form
from fastapi.responses import HTMLResponse
from plugin_context import PluginContext


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


# ============================================================
# ROUTE REGISTRATION (Contract v2 Schema)
# ============================================================

def register_routes(app, templates, get_host):
    """
    Registers the plugin's internal POST routes dynamically.
    This makes main.py completely independent of this plugin's forms.
    """
    
    @app.post("/plugin/news_scanner/fetch", response_class=HTMLResponse)
    async def fetch_news_results(
        request: Request, 
        watchlist_item: str = Form(None), 
        custom_query: str = Form(None)
    ):
        # 1. Determine the final search query strings
        query = custom_query.strip() if custom_query else watchlist_item
        host = get_host(request)
        
        # 2. Extract plugin instance context variables
        plugin_module = host.plugins["news_scanner"]["module"]
        context = PluginContext(host) 
        
        # 3. Process the backend business request
        result = plugin_module.handle_request({"payload": {"query": query}}, context)
        
        # 4. Map the payload context parameters cleanly for the sub-template
        context_data = {
            "query": query,
            "articles": result.get("data", []) if result.get("status") == "success" else [],
            "error": result.get("message") if result.get("status") == "error" else None
        }
        
        # 5. Resolve template directly via the passed templates loader instance
        target_template = "news_scanner_results.html"
        try:
            # Test if the flat template can be matched by Jinja's active loaders
            templates.env.loader.load(templates.env, target_template)
        except Exception:
            # Fallback string if something goes wrong
            target_template = "partials/news_scanner_results.html"
        
        return templates.TemplateResponse(
            request=request,
            name=target_template,
            context=context_data
        )

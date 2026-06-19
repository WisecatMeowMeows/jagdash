# plugins/c0rdin8/c0rdin8_plugin.py
# Coordinated Signal Feed Plugin for NiteTrader

import os
import requests
from fastapi import Request, Form
from fastapi.responses import HTMLResponse
from plugin_context import PluginContext

DEFAULT_FEEDS = [
    "http://127.0.0.1:5000/feed/wsb.json",
    "http://127.0.0.1:5000/feed/crypto.json",
]


def manifest():
    return {
        "name": "c0rdin8",
        "version": "2.0",  # Upgraded to contract v2
        "provides": [
            "feed.fetch",
            "feed.fetch_all"
        ],
        "requires": []
    }


def _handle_feed_fetch(payload, context):
    url = payload.get("feed_url")
    if not url:
        return {
            "status": "error",
            "message": "feed_url missing"
        }

    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()

        return {
            "status": "success",
            "feed": {
                "feed_id": data.get("feed_id"),
                "feed_name": data.get("feed_name"),
                "publisher": data.get("publisher"),
                "signal_count": data.get("signal_count", 0),
            },
            "data": data.get("signals", [])
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }


def _handle_fetch_all(payload, context):
    all_signals = []
    for url in DEFAULT_FEEDS:
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()

            for signal in data.get("signals", []):
                signal["_feed_name"] = data.get("feed_name")
                all_signals.append(signal)
        except Exception:
            pass

    return {
        "status": "success",
        "data": all_signals
    }


def handle_request(request, context):
    capability = request.get("capability")
    payload = request.get("payload", {})

    if capability == "feed.fetch":
        return _handle_feed_fetch(payload, context)

    if capability == "feed.fetch_all":
        return _handle_fetch_all(payload, context)

    return {
        "status": "error",
        "message": f"Unsupported capability: {capability}"
    }


# ============================================================
# ROUTE REGISTRATION (Contract v2 Schema)
# ============================================================

def register_routes(app, templates, get_host):
    """Dynamically binds HTMX form post routes to handle coordinate tracking queries."""
    
    @app.post("/plugin/c0rdin8/fetch", response_class=HTMLResponse)
    async def fetch_feed_signals(
        request: Request,
        feed_url: str = Form(None)
    ):
        host = get_host(request)
        context = PluginContext(host)
        plugin_module = host.plugins["c0rdin8"]["module"]
        
        # If no explicit path is passed, default to scanning the first fallback item array
        target_url = feed_url.strip() if feed_url else DEFAULT_FEEDS[0]
        
        # 1. Trigger internal fetch sequence matching handle_request standard format
        req_payload = {
            "capability": "feed.fetch",
            "payload": {"feed_url": target_url}
        }
        result = plugin_module.handle_request(req_payload, context)
        
        # 2. Extract feed header info and coordinate details arrays
        feed_info = result.get("feed", {}) if result.get("status") == "success" else {}
        signals_list = result.get("data", []) if result.get("status") == "success" else []
        
        # 3. Consolidate context state keys for template data rendering blocks
        context_envelope = {
            "feed_url": target_url,
            "feed": feed_info,
            "signals": signals_list,
            "default_feeds": DEFAULT_FEEDS,
            "error": result.get("message") if result.get("status") == "error" else None
        }
        
        # 4. Resolve sub-template path targets safely inside layout spaces
        target_template = "c0rdin8_results.html"
        try:
            templates.env.loader.load(templates.env, target_template)
        except Exception:
            target_template = "partials/c0rdin8_results.html"
            
        return templates.TemplateResponse(
            request=request,
            name=target_template,
            context=context_envelope
        )

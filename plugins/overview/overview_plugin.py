"""
plugins/overview/overview_plugin.py — NiteTrader Overview Plugin

Aggregates the most important output from every other plugin into a compact
summary. Calls existing capabilities — no logic duplicated here.

Provides: overview.summary
Requires: market.price, market.strategy.signal, news.signal, news.headlines
"""

import os
from fastapi import Request, Form
from fastapi.responses import HTMLResponse
from plugin_context import PluginContext


def manifest():
    return {
        "name":     "overview",
        "version":  "2.0",  # Upgraded to contract v2
        "provides": ["overview.summary"],
        "requires": [
            "market.price",
            "market.strategy.signal",
            "news.signal",
            "news.headlines",
        ],
    }


def handle_request(request, context):
    capability = request.get("capability")
    if capability != "overview.summary":
        return {"status": "error", "message": f"Unsupported capability: {capability}"}

    payload    = request.get("payload", {})
    symbol     = payload.get("symbol",     "BTC-USD")
    news_query = payload.get("news_query", "Bitcoin")
    interval   = payload.get("interval",   "5m")
    period     = payload.get("period",     "1mo")

    results = {}

    # --- Market price ---
    try:
        r = context.request("market.price", {
            "symbol": symbol, "interval": interval,
            "period": period, "include_ohlcv": True,
        })
        if r["status"] == "success" and r["data"]:
            records    = r["data"]
            first_close = records[0]["close"]
            last_close  = records[-1]["close"]
            pct_change  = ((last_close - first_close) / first_close * 100
                           if first_close else 0.0)
            results["market_price"] = {
                "symbol":     symbol,
                "price":      last_close,
                "pct_change": round(pct_change, 2),
                "candles":    len(records),
                "interval":   interval,
                "period":     period,
            }
        else:
            results["market_price"] = {"error": r.get("message", "No data")}
    except Exception as e:
        results["market_price"] = {"error": str(e)}

    # --- Strategy signal ---
    try:
        r = context.request("market.strategy.signal", {
            "symbol": symbol, "interval": interval, "period": period,
        })
        if r["status"] == "success":
            data = r["data"]
            results["strategy"] = {
                "symbol":     symbol,
                "signal":     data["combined"]["signal"],
                "score":      data["combined"]["score"],
                "confidence": data["combined"]["confidence"],
                "candles":    data.get("candle_count", "?"),
            }
        else:
            results["strategy"] = {"error": r.get("message", "Failed")}
    except Exception as e:
        results["strategy"] = {"error": str(e)}

    # --- News signal ---
    try:
        r = context.request("news.signal", {"query": news_query})
        if r["status"] == "success":
            data = r["data"]
            results["news_signal"] = {
                "query":         news_query,
                "signal":        data.get("signal", "NEUTRAL"),
                "bullish_total": data.get("bullish_total", 0),
                "bearish_total": data.get("bearish_total", 0),
                "article_count": len(data.get("articles", [])),
            }
        else:
            results["news_signal"] = {"error": r.get("message", "Failed")}
    except Exception as e:
        results["news_signal"] = {"error": str(e)}

    # --- News headlines ---
    try:
        r = context.request("news.headlines", {"symbol": news_query})
        if r["status"] == "success":
            headlines = r["data"].get("headlines", [])
            results["news_headlines"] = {
                "query":     news_query,
                "headlines": headlines[:3],
            }
        else:
            results["news_headlines"] = {"error": r.get("message", "Failed")}
    except Exception as e:
        results["news_headlines"] = {"error": str(e)}

    return {
        "status": "success",
        "data": {
            "symbol":     symbol,
            "news_query": news_query,
            "interval":   interval,
            "period":     period,
            "results":    results,
        }
    }


def get_ui_context(context):
    try:
        profile  = context.get_active_profile()
        settings = profile.get("overview", {})
    except Exception:
        settings = {}
        
    # Standardised read defaults to feed directly into overview.html layout
    return {
        "ov_symbol":   settings.get("symbol",     "BTC-USD"),
        "ov_query":    settings.get("news_query",  "Bitcoin"),
        "ov_interval": settings.get("interval",    "5m"),
        "ov_period":   settings.get("period",      "1mo"),
    }


# ============================================================
# ROUTE REGISTRATION (Contract v2 Schema)
# ============================================================

def register_routes(app, templates, get_host):
    """Dynamically binds HTMX form post handling routes for the overview metrics."""
    
    @app.post("/plugin/overview/fetch", response_class=HTMLResponse)
    async def fetch_overview_summary(
        request: Request,
        symbol: str = Form("BTC-USD"),
        news_query: str = Form("Bitcoin"),
        interval: str = Form("5m"),
        period: str = Form("1mo")
    ):
        host = get_host(request)
        context = PluginContext(host)
        plugin_module = host.plugins["overview"]["module"]
        
        # 1. Build request dictionary matching handle_request expectations
        req_payload = {
            "capability": "overview.summary",
            "payload": {
                "symbol": symbol.strip(),
                "news_query": news_query.strip(),
                "interval": interval.strip(),
                "period": period.strip()
            }
        }
        
        # 2. Extract freshly aggregated capabilities metrics
        result = plugin_module.handle_request(req_payload, context)
        metrics_data = result.get("data", {}).get("results", {}) if result.get("status") == "success" else {}
        
        # 3. Form a clean context envelope for the template partial
        # FIX: Changed key "metrics" to "results" to perfectly match your overview_results.html template variables!
        context_envelope = {
            "query": news_query,
            "symbol": symbol,
            "interval": interval,
            "period": period,
            "results": metrics_data, 
            "error": result.get("message") if result.get("status") == "error" else None
        }
        
        # 4. Target the data sub-template to drop cleanly into #overview-results
        target_template = "overview_results.html"
        try:
            templates.env.loader.load(templates.env, target_template)
        except Exception:
            target_template = "partials/overview_results.html"
            
        return templates.TemplateResponse(
            request=request,
            name=target_template,
            context=context_envelope
        )

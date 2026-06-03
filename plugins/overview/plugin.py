"""
plugins/overview/plugin.py — JagDash Overview Plugin

Aggregates the most important output from every other plugin into a compact
summary. Calls existing capabilities — no logic duplicated here.

Provides: overview.summary
Requires: market.price, market.strategy.signal, news.signal, news.headlines
"""


def manifest():
    return {
        "name":     "overview",
        "version":  "1.0",
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
    return {
        "ov_symbol":   settings.get("symbol",     "BTC-USD"),
        "ov_query":    settings.get("news_query",  "Bitcoin"),
        "ov_interval": settings.get("interval",    "5m"),
        "ov_period":   settings.get("period",      "1mo"),
    }

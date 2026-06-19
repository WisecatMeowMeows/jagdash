# market_data/plugin.py
# JagDash Market Data Plugin v1.3
#
# Provides: market.price   — fetch OHLCV history from multiple sources
#           market.settings — return current UI configuration (for sync)

import pandas as pd
import re as _re
import importlib.util
import pathlib


# ---------------------------------------------------------------------------
# Load sources.py from the same directory as this plugin file.
# Uses importlib so we don't need __init__.py or sys.path manipulation.
# ---------------------------------------------------------------------------

def _load_sources():
    src_path = pathlib.Path(__file__).parent / "sources.py"
    spec     = importlib.util.spec_from_file_location("market_data_sources", src_path)
    mod      = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_sources      = _load_sources()
_fetch_source = _sources.fetch
SOURCE_LABELS = _sources.SOURCE_LABELS
SOURCE_NOTES  = _sources.SOURCE_NOTES


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# yfinance-specific valid values — only used when source == "yahoo"
VALID_PERIODS_YF   = ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"]
VALID_INTERVALS_YF = ["1m","2m","5m","15m","30m","60m","90m","1h",
                      "1d","5d","1wk","1mo","3mo"]

INTRADAY_PERIOD_LIMITS = {
    "1m": "7d", "2m": "60d", "5m": "60d", "15m": "60d",
    "30m": "60d", "60m": "730d", "90m": "60d", "1h": "730d",
}

DEFAULT_PERIOD   = "1mo"
DEFAULT_INTERVAL = "5m"
DEFAULT_SYMBOL   = "BTC-USD"
DEFAULT_SOURCE   = "yahoo"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def manifest():
    return {
        "name":     "market_data",
        "version":  "1.3",
        "provides": ["market.price", "market.settings"],
        "requires": [],
        "ui_defaults": {
            "symbol":   DEFAULT_SYMBOL,
            "interval": DEFAULT_INTERVAL,
            "period":   DEFAULT_PERIOD,
            "source":   DEFAULT_SOURCE,
            "range_mode": "period",
            "start":      "",
            "end":        "",
        }
    }


# ---------------------------------------------------------------------------
# get_ui_context — passes source options to the template
# ---------------------------------------------------------------------------

def get_ui_context(context):
    # Use already-loaded _sources module — no re-import needed
    source_options = [
        {"value": k, "label": v, "note": SOURCE_NOTES.get(k, "")}
        for k, v in SOURCE_LABELS.items()
    ]
    return {"source_options": source_options}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_asset_class(symbol: str) -> str:
    if _re.search(r'-(USD|USDT|BTC|ETH|USDC)$', symbol, _re.I):
        return "crypto"
    if _re.search(r'=X$', symbol):
        return "forex"
    if _re.search(r'=F$', symbol):
        return "futures"
    return "equity"


def _validate_yfinance_params(period, interval, start, end):
    """
    Validate period/interval only for Yahoo Finance.
    Other sources have their own valid ranges handled in sources.py.
    Returns (ok: bool, message: str).
    """
    if interval not in VALID_INTERVALS_YF:
        return False, (f"Interval '{interval}' not supported by Yahoo Finance. "
                       f"Choose from: {VALID_INTERVALS_YF}")
    if not (start or end):
        if period not in VALID_PERIODS_YF:
            return False, (f"Period '{period}' not supported by Yahoo Finance. "
                           f"Choose from: {VALID_PERIODS_YF}")
        if interval in INTRADAY_PERIOD_LIMITS:
            limit      = INTRADAY_PERIOD_LIMITS[interval]
            limit_days = _period_to_approx_days(limit)
            req_days   = _period_to_approx_days(period)
            if req_days > limit_days:
                return False, (
                    f"Yahoo Finance interval '{interval}' only supports up to "
                    f"{limit} of history. Reduce period or use a larger interval."
                )
    else:
        if start and end:
            try:
                s = pd.Timestamp(start)
                e = pd.Timestamp(end)
                if s >= e:
                    return False, "start date must be before end date."
            except Exception:
                return False, "Invalid start/end date format. Use YYYY-MM-DD."
    return True, ""


def _period_to_approx_days(period_str: str) -> int:
    table = {
        "1d": 1, "5d": 5, "7d": 7,
        "1mo": 30, "2mo": 60, "3mo": 90, "6mo": 180,
        "60d": 60, "730d": 730,
        "1y": 365, "2y": 730, "5y": 1825, "10y": 3650,
        "ytd": 365, "max": 99999,
    }
    return table.get(period_str, 99999)


# ---------------------------------------------------------------------------
# Capability handlers
# ---------------------------------------------------------------------------

def _handle_market_price(payload: dict, context) -> dict:
    symbol   = payload.get("symbol",        DEFAULT_SYMBOL)
    period   = payload.get("period",        DEFAULT_PERIOD)
    interval = payload.get("interval",      DEFAULT_INTERVAL)
    start    = payload.get("start",         None)
    end      = payload.get("end",           None)
    source   = payload.get("source",        DEFAULT_SOURCE)

    # Validate params only for Yahoo Finance — other sources handle their own limits
    if source == "yahoo":
        ok, msg = _validate_yfinance_params(period, interval, start, end)
        if not ok:
            return {"status": "error", "message": msg}

    cmc_key = context.get_api_key("coinmarketcap") if source == "coinmarketcap" else ""

    try:
        records = _fetch_source(
            source=source, symbol=symbol, period=period,
            interval=interval, start=start, end=end, api_key=cmc_key,
        )
    except Exception as e:
        return {"status": "error", "message": f"{source} fetch failed: {e}"}

    if records is None:
        return {
            "status":  "error",
            "message": f"No data returned for '{symbol}' from {SOURCE_LABELS.get(source, source)}."
        }

    # Detect and strip the internal CMC free-tier flag
    cmc_free_tier = (
        source == "coinmarketcap"
        and len(records) == 1
        and records[0].get("_cmc_free_tier", False)
    )
    for r in records:
        r.pop("_cmc_free_tier", None)

    context.publish("market.tick", {"symbol": symbol, "price": records[-1]["close"]})

    _ts_key = next(
        (k for k in ["date","Date","datetime","timestamp","Datetime"]
         if k in records[0]),
        None,
    ) if records else None

    result = {
        "status": "success",
        "data":   records,
        "meta": {
            "symbol":       symbol,
            "period":       period if not (start or end) else None,
            "interval":     interval,
            "start":        start,
            "end":          end,
            "candles":      len(records),
            "columns":      list(records[0].keys()) if records else [],
            "source":       source,
            "source_label": SOURCE_LABELS.get(source, source),
            "cmc_free_tier": cmc_free_tier,
            "asset_class":  _detect_asset_class(symbol),
            "date_from":    str(records[0][_ts_key])  if (_ts_key and records) else None,
            "date_to":      str(records[-1][_ts_key]) if (_ts_key and records) else None,
        },
    }

    # Attach warning for CMC free-tier — now correctly AFTER result is built
    if cmc_free_tier:
        result["warning"] = (
            "CoinMarketCap free tier: only current price returned. "
            "Historical OHLCV candles require a paid Hobbyist plan. "
            "Strategy analysis will not work with 1 candle."
        )

    return result


def _handle_market_settings(payload: dict, context) -> dict:
    """
    Return the last-used market data settings so other plugins can sync.
    Reads from the host's shared _market_settings dict, which is updated
    every time the market_data fetch route is called.
    Falls back to manifest defaults if no fetch has been made yet.
    """
    # Read from host shared state (set by register_routes fetch handler)
    try:
        stored = getattr(context.host, "_market_settings", {})
    except Exception:
        stored = {}

    return {
        "status": "success",
        "data": {
            "symbol":   stored.get("symbol",   DEFAULT_SYMBOL),
            "interval": stored.get("interval", DEFAULT_INTERVAL),
            "period":   stored.get("period",   DEFAULT_PERIOD),
            "source":   stored.get("source",   DEFAULT_SOURCE),
        },
    }


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------

def handle_request(request, context):
    capability = request.get("capability")
    payload    = request.get("payload", {})

    if capability == "market.price":
        return _handle_market_price(payload, context)

    if capability == "market.settings":
        return _handle_market_settings(payload, context)

    return {
        "status":  "error",
        "message": (f"Unsupported capability: '{capability}'. "
                    f"Provides: market.price, market.settings"),
    }


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def register_routes(app, templates, get_host):
    from fastapi import Form, Request
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext

    def _save_state(request, values: dict) -> None:
        request.session["ui_market_data"] = values

    @app.post("/plugin/market_data/fetch", response_class=HTMLResponse)
    async def market_data_fetch(
        request:  Request,
        symbol:   str = Form(DEFAULT_SYMBOL),
        period:   str = Form(DEFAULT_PERIOD),
        interval: str = Form(DEFAULT_INTERVAL),
        source:   str = Form(DEFAULT_SOURCE),
        range_mode: str = Form("period"),
        start:    str = Form(""),
        end:      str = Form(""),
    ):
        _save_state(request, {
            "symbol": symbol, 
            "period": period,
            "interval": interval, 
            "source": source,
            "range_mode": range_mode,
            "start": start, 
            "end": end,

        })

        # Write to host shared state so market.settings can return
        # current values to other plugins (e.g. strategy_engine)
        host = get_host(request)
        host._market_settings = {
            "symbol": symbol, "interval": interval,
            "period": period, "source": source,
        }

        host    = get_host(request)
        context = PluginContext(host)

        try:
            result = context.request("market.price", {
                "symbol":           symbol, 
                "period":           period,
                "interval":         interval, 
                "include_ohlcv":    True,
                "source":           source,
                "start":            start if range_mode == "dates" else None,
                "end":              end   if range_mode == "dates" else None,
            })
        except Exception as e:
            return HTMLResponse(f'<div class="error-msg">Request failed: {e}</div>')

        if result["status"] != "success":
            return HTMLResponse(f'<div class="error-msg">{result["message"]}</div>')

        records = result["data"]
        meta    = result.get("meta", {})

        return templates.TemplateResponse(
            request=request,
            name="market_data_results.html",
            context={
                "symbol":       symbol,
                "source_label": meta.get("source_label", SOURCE_LABELS.get(source, source)),
                "records":      records,
                "meta":         meta,
                "latest_close": records[-1]["close"] if records else None,
                "candle_count": len(records),
                "warning":      result.get("warning"),
            }
        )

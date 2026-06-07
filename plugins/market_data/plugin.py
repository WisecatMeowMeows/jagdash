# market_data/plugin.py
# JagDash Market Data Plugin v1.2
# NiteTrader Plugin Ecosystem
#
# Provides: market.price   — fetch OHLCV history via yfinance
#           market.settings — return current UI configuration (for sync)


import yfinance as yf
import pandas as pd
import re as _re

# ---------------------------------------------------------------------------
# Valid yfinance period / interval combinations.
# yfinance enforces limits: intraday history only goes back ~60 days for 1h,
# ~7 days for sub-hourly intervals.
# ---------------------------------------------------------------------------
VALID_PERIODS   = ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"]
VALID_INTERVALS = ["1m","2m","5m","15m","30m","60m","90m","1h",
                   "1d","5d","1wk","1mo","3mo"]

# Intraday intervals and the max lookback yfinance supports for each.
INTRADAY_PERIOD_LIMITS = {
    "1m":  "7d",
    "2m":  "60d",
    "5m":  "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "90m": "60d",
    "1h":  "730d",
}

DEFAULT_PERIOD   = "5y"
DEFAULT_INTERVAL = "1d"
DEFAULT_SYMBOL   = "BTC-USD"

# Session-state keys used by render_ui — must match what _handle_market_settings reads.
_KEY_SYMBOL   = "md_symbol"
_KEY_INTERVAL = "md_interval"
_KEY_PERIOD   = "md_period"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def manifest():
    return {
        "name":     "market_data",
        "version":  "1.2",
        "provides": [
            "market.price",
            "market.settings",
        ],
        "requires": [],
        "ui_defaults": {          
            "symbol":   "BTC-USD",
            "interval": "5m",
            "period":   "1mo",
        }
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _detect_asset_class(symbol: str) -> str:
    """
    Lightweight heuristic for display purposes.
    yfinance symbol conventions:
      BTC-USD, ETH-USDT, ...  → crypto
      EURUSD=X, GBPJPY=X, ... → forex
      GC=F, CL=F, ...         → futures
      everything else         → equity
    """
    if _re.search(r'-(USD|USDT|BTC|ETH|USDC)$', symbol, _re.I):
        return "crypto"
    if _re.search(r'=X$', symbol):
        return "forex"
    if _re.search(r'=F$', symbol):
        return "futures"
    return "equity"


def _validate_params(period, interval, start, end):
    """
    Sanity-check period/interval combo.
    Returns (ok: bool, message: str).
    """
    if interval not in VALID_INTERVALS:
        return False, f"Invalid interval '{interval}'. Choose from: {VALID_INTERVALS}"

    if not (start or end):
        if period not in VALID_PERIODS:
            return False, f"Invalid period '{period}'. Choose from: {VALID_PERIODS}"
        if interval in INTRADAY_PERIOD_LIMITS:
            limit      = INTRADAY_PERIOD_LIMITS[interval]
            limit_days = _period_to_approx_days(limit)
            req_days   = _period_to_approx_days(period)
            if req_days > limit_days:
                return False, (
                    f"Interval '{interval}' only supports up to {limit} of history. "
                    f"Reduce period or use a larger interval."
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
    """Rough conversion so we can compare limits — not exact, just safe."""
    table = {
        "1d": 1,    "5d": 5,    "7d": 7,
        "1mo": 30,  "2mo": 60,  "3mo": 90,  "6mo": 180,
        "60d": 60,  "730d": 730,
        "1y": 365,  "2y": 730,  "5y": 1825, "10y": 3650,
        "ytd": 365, "max": 99999,
    }
    return table.get(period_str, 99999)


def _fetch_history(symbol, period=DEFAULT_PERIOD, interval=DEFAULT_INTERVAL,
                   start=None, end=None, include_ohlcv=True):
    """
    Core yfinance fetch. Returns a list of record dicts, or None on empty result.

    Priority:
      1. start/end date range (ignores period when either is set)
      2. period string

    Output columns (include_ohlcv=True):  open, high, low, close, volume
    Output columns (include_ohlcv=False): close only (v1.1 compat)
    """
    ticker = yf.Ticker(symbol)

    kwargs = {"interval": interval, "auto_adjust": True}
    if start or end:
        if start: kwargs["start"] = start
        if end:   kwargs["end"]   = end
    else:
        kwargs["period"] = period

    hist = ticker.history(**kwargs)

    if hist.empty:
        return None

    hist.columns = [c.lower() for c in hist.columns]

    if include_ohlcv:
        cols = [c for c in ["open","high","low","close","volume"] if c in hist.columns]
    else:
        cols = ["close"]

    # Preserve the index (Date/Datetime) as a column so consumers get timestamps
    hist = hist[cols].copy()
    hist.index.name = "date"
    records = hist.reset_index().to_dict(orient="records")

    # Stringify the date so it's JSON-serialisable
    for r in records:
        if "date" in r:
            r["date"] = str(r["date"])

    return records


# ---------------------------------------------------------------------------
# Capability handlers
# ---------------------------------------------------------------------------

def _handle_market_price(payload: dict, context) -> dict:
    """Fetch and return OHLCV history for a symbol."""
    symbol        = payload.get("symbol",        DEFAULT_SYMBOL)
    period        = payload.get("period",        DEFAULT_PERIOD)
    interval      = payload.get("interval",      DEFAULT_INTERVAL)
    start         = payload.get("start",         None)
    end           = payload.get("end",           None)
    include_ohlcv = payload.get("include_ohlcv", True)

    ok, msg = _validate_params(period, interval, start, end)
    if not ok:
        return {"status": "error", "message": msg}

    try:
        records = _fetch_history(
            symbol, period=period, interval=interval,
            start=start, end=end, include_ohlcv=include_ohlcv,
        )
    except Exception as e:
        return {"status": "error", "message": f"yfinance fetch failed: {e}"}

    if records is None:
        return {"status": "error", "message": f"No data returned for symbol: {symbol}"}

    context.publish(
        "market.tick",
        {"symbol": symbol, "price": records[-1]["close"]},
    )

    # Actual date range from records (more reliable than requested start/end)
    _ts_key = next(
        (k for k in ["date","Date","datetime","timestamp","Datetime"]
         if k in records[0]),
        None,
    ) if records else None

    return {
        "status": "success",
        "data":   records,
        "meta": {
            "symbol":      symbol,
            "period":      period if not (start or end) else None,
            "interval":    interval,
            "start":       start,
            "end":         end,
            "candles":     len(records),
            "columns":     list(records[0].keys()) if records else [],
            "source":      "yfinance",
            "asset_class": _detect_asset_class(symbol),
            "date_from":   str(records[0][_ts_key])  if (_ts_key and records) else None,
            "date_to":     str(records[-1][_ts_key]) if (_ts_key and records) else None,
        },
    }


def _handle_market_settings() -> dict:
    """
    Return the current UI configuration so other plugins can sync to it.
    Reads from session_state (set by render_ui widgets) with fallback to defaults.
    """
    return {
        "status": "success",
        "data": {
            "symbol":   st.session_state.get(_KEY_SYMBOL,   DEFAULT_SYMBOL),
            "interval": st.session_state.get(_KEY_INTERVAL, DEFAULT_INTERVAL),
            "period":   st.session_state.get(_KEY_PERIOD,   DEFAULT_PERIOD),
        },
    }


# ---------------------------------------------------------------------------
# Plugin interface — dispatch on capability
# ---------------------------------------------------------------------------

def handle_request(request, context):
    capability = request.get("capability")
    payload    = request.get("payload", {})

    if capability == "market.price":
        return _handle_market_price(payload, context)

    if capability == "market.settings":
        return _handle_market_settings()

    return {
        "status":  "error",
        "message": f"Unsupported capability: '{capability}'. "
                   f"Provides: market.price, market.settings",
    }

def register_routes(app, templates, get_host):
    """
    Register this plugin's HTTP routes directly onto the FastAPI app.

    Called once at JagDash startup by main.py's lifespan function.
    This means main.py never needs to know about market_data's form fields,
    capability names, or template names.

    The function signature (app, templates, get_host) is the standard
    JagDash plugin route registration contract. Every plugin that registers
    routes must accept these three arguments:
        app         — the FastAPI application instance
        templates   — the Jinja2Templates instance for rendering HTML
        get_host    — function(request) -> PluginHost, for accessing plugins

    Why import inside the function?
    FastAPI, Form, HTMLResponse, etc. are only needed when routes are being
    registered — not when the plugin is doing its data work in handle_request().
    Keeping these imports local means the plugin's core logic has no web
    framework dependency, which makes it easier to test in isolation.
    """
    from fastapi import Form, Request
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext

    # Import save_plugin_state from main — but we can't import main directly
    # (circular import). Instead, duplicate the minimal state-saving logic.
    # This is the one unavoidable trade-off of the register_routes pattern.
    def _save_state(request, values: dict) -> None:
        request.session["ui_market_data"] = values

    @app.post("/plugin/market_data/fetch", response_class=HTMLResponse)
    async def market_data_fetch(
        request:  Request,
        symbol:   str = Form("BTC-USD"),
        period:   str = Form("1mo"),
        interval: str = Form("5m"),
    ):
        # Save submitted values to session so the form restores them on reload
        _save_state(request, {
            "symbol": symbol, "period": period, "interval": interval
        })

        host    = get_host(request)
        context = PluginContext(host)

        try:
            result = context.request("market.price", {
                "symbol":        symbol,
                "period":        period,
                "interval":      interval,
                "include_ohlcv": True,
            })
        except Exception as e:
            return HTMLResponse(
                content=f'<div class="error-msg">Request failed: {e}</div>'
            )

        if result["status"] != "success":
            return HTMLResponse(
                content=f'<div class="error-msg">{result["message"]}</div>'
            )

        records = result["data"]
        return templates.TemplateResponse(
            request=request,
            name="partials/market_data_results.html",
            context={
                "symbol":      symbol,
                "records":     records,
                "meta":        result.get("meta", {}),
                "latest_close": records[-1]["close"] if records else None,
                "candle_count": len(records),
            }
        )

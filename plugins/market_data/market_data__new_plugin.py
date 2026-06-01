# market_data/plugin.py
# JagDash Market Data Plugin v1.2
# NiteTrader Plugin Ecosystem
#
# Provides: market.price   — fetch OHLCV history via yfinance
#           market.settings — return current UI configuration (for sync)

import streamlit as st
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
        "requires": []
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


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def render_ui(context):
    st.subheader("Market Data Plugin")

    # ── Persist settings across plugin switches ───────────────────────────
    # Streamlit deletes session_state values for keyed widgets whenever those
    # widgets are not rendered (e.g. when the user switches to another plugin).
    # Fix: no key= on any widget; we initialise with setdefault and write back
    # manually.  Values stored this way are never owned by a widget, so
    # Streamlit never clears them on navigation.
    _interval_opts = ["1d","1wk","1mo","1h","30m","15m","5m","1m"]
    _period_opts   = ["5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"]
    _mode_opts     = ["Period", "Date range"]

    st.session_state.setdefault(_KEY_SYMBOL,    DEFAULT_SYMBOL)
    st.session_state.setdefault(_KEY_INTERVAL,  DEFAULT_INTERVAL)
    st.session_state.setdefault(_KEY_PERIOD,    DEFAULT_PERIOD)
    st.session_state.setdefault("md_fetch_mode", "Period")

    # ── Symbol & interval ─────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        symbol = st.text_input(
            "Symbol",
            value=st.session_state[_KEY_SYMBOL],
            help="Yahoo Finance symbol. Examples: AAPL, ETH-USD, ^GSPC",
        )
        st.session_state[_KEY_SYMBOL] = symbol

    with col2:
        _int_cur = st.session_state[_KEY_INTERVAL]
        interval = st.selectbox(
            "Interval",
            options=_interval_opts,
            index=_interval_opts.index(_int_cur)
                  if _int_cur in _interval_opts else 0,
            help="Bar size. Sub-hour intervals have shorter max lookback.",
        )
        st.session_state[_KEY_INTERVAL] = interval

    # ── Date range vs period toggle ────────────────────────────────────────
    _mode_cur  = st.session_state["md_fetch_mode"]
    fetch_mode = st.radio(
        "Lookback mode", _mode_opts,
        index=_mode_opts.index(_mode_cur) if _mode_cur in _mode_opts else 0,
        horizontal=True,
    )
    st.session_state["md_fetch_mode"] = fetch_mode

    period = st.session_state[_KEY_PERIOD]
    start  = None
    end    = None

    if fetch_mode == "Period":
        _per_cur = st.session_state[_KEY_PERIOD]
        period = st.selectbox(
            "Period",
            options=_period_opts,
            index=_period_opts.index(_per_cur)
                  if _per_cur in _period_opts else 4,
        )
        st.session_state[_KEY_PERIOD] = period
    else:
        dcol1, dcol2 = st.columns(2)
        with dcol1:
            start = st.date_input("Start date").strftime("%Y-%m-%d")
        with dcol2:
            end   = st.date_input("End date").strftime("%Y-%m-%d")

    # ── Options ───────────────────────────────────────────────────────────
    include_ohlcv = st.checkbox(
        "Include full OHLCV", value=True,
        help="Unchecked = close-only (smaller payload)",
    )

    # ── Fetch ─────────────────────────────────────────────────────────────
    if st.button("Fetch Data", type="primary"):
        with st.spinner("Fetching…"):
            try:
                result = context.request(
                    "market.price",
                    {
                        "symbol":        symbol,
                        "period":        period,
                        "interval":      interval,
                        "start":         start,
                        "end":           end,
                        "include_ohlcv": include_ohlcv,
                    },
                )
            except Exception as e:
                st.error(f"Request failed: {e}")
                return

        if result["status"] == "success":
            records = result["data"]
            meta    = result.get("meta", {})
            latest  = records[-1]["close"]

            st.metric(
                label=f"{symbol} latest close",
                value=f"${latest:,.2f}",
            )

            cols = meta.get("columns", [])
            st.caption(
                f"{meta.get('candles', len(records))} candles  |  "
                f"interval: {meta.get('interval', interval)}  |  "
                f"columns: {', '.join(cols)}  |  "
                f"source: {meta.get('source', '?')}  |  "
                f"asset class: {meta.get('asset_class', '?')}"
            )

            df = pd.DataFrame(records)
            st.dataframe(df, width='stretch')

        else:
            st.error(result["message"])

"""
market_data_sources.py
======================
Data source fetch functions for the market_data plugin.
Each source returns data in the standard market.price format:
    list of dicts with keys: open, high, low, close, volume, date

Adding a new source:
  1. Write a _fetch_{source}() function following the contract below
  2. Add it to SOURCES dict at the bottom
  3. Add the source name to manifest() ui_defaults in plugin.py

Fetch function contract:
  def _fetch_mysource(symbol, period, interval, start, end) -> list[dict] | None
  - Returns list of OHLCV dicts, or None if no data
  - Raises Exception on error (caller handles it)
  - All timestamps normalized to ISO string in "date" field
  - All numeric fields are Python floats
"""

import requests
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# INTERVAL MAPPING HELPERS
# Different exchanges use different interval string formats.
# ---------------------------------------------------------------------------

def _hl_interval(interval: str) -> str:
    """
    Convert JagDash interval strings to Hyperliquid format.
    Hyperliquid uses: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 12h, 1d, 3d, 1w
    """
    mapping = {
        "1m": "1m", "2m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "60m": "1h", "90m": "1h", "1h": "1h", "1d": "1d", "1wk": "1w",
        "1mo": "1d",   # no monthly candles; use daily
    }
    return mapping.get(interval, "1h")


def _period_to_ms(period: str) -> tuple[int, int]:
    """
    Convert a period string to (start_ms, end_ms) epoch milliseconds.
    Used for APIs that take explicit time ranges.
    """
    end   = datetime.now(timezone.utc)
    delta_map = {
        "1d": timedelta(days=1),
        "5d": timedelta(days=5),
        "1mo": timedelta(days=30),
        "3mo": timedelta(days=90),
        "6mo": timedelta(days=180),
        "1y":  timedelta(days=365),
        "2y":  timedelta(days=730),
        "5y":  timedelta(days=1825),
    }
    delta = delta_map.get(period, timedelta(days=30))
    start = end - delta
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


# ---------------------------------------------------------------------------
# SOURCE: Yahoo Finance (via yfinance)
# ---------------------------------------------------------------------------

def _fetch_yfinance(symbol, period, interval, start, end):
    """
    Original Yahoo Finance source via yfinance library.
    Handles stocks, crypto (BTC-USD), forex, futures.
    """
    import yfinance as yf
    import pandas as pd

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

    hist.columns  = [c.lower() for c in hist.columns]
    cols          = [c for c in ["open","high","low","close","volume"] if c in hist.columns]
    hist          = hist[cols].copy()
    hist.index.name = "date"
    records       = hist.reset_index().to_dict(orient="records")

    for r in records:
        if "date" in r:
            r["date"] = str(r["date"])
    return records


# ---------------------------------------------------------------------------
# SOURCE: Hyperliquid
# ---------------------------------------------------------------------------

def _fetch_hyperliquid(symbol, period, interval, start, end):
    """
    Hyperliquid perpetuals exchange.
    Public API — no key required.
    Endpoint: POST https://api.hyperliquid.xyz/info

    Symbol format: coin name only, e.g. "BTC", "ETH", "SOL"
    Strip any suffix the user may have typed (BTC-USD → BTC, BTC/USDC → BTC).

    Returns up to 5000 candles. Hyperliquid covers perpetual futures only —
    not available for traditional stocks, forex, or non-listed tokens.

    Candle fields from API: t (open time ms), T (close time ms),
    o (open), h (high), l (low), c (close), v (volume), n (trades)
    """
    # Normalize symbol for Hyperliquid.
    #
    # Standard perps: just the uppercase coin name
    #   BTC-USD → BTC,  ETH → ETH
    #
    # HIP-3 deployer perps use dex:TICKER format (lowercase dex, uppercase ticker)
    #   xyz:BRENTOIL → xyz:BRENTOIL  (preserve as-is, just uppercase ticker)
    #   XYZ:BRENTOIL → xyz:BRENTOIL  (lowercase the dex prefix)
    #   BRENTOIL     → BRENTOIL      (no prefix: pass bare, let API return 500
    #                                  with a clear error if not found)
    #
    # Do NOT strip the dex: prefix — it is required for HIP-3 assets.
    if ":" in symbol:
        # Has deployer prefix — preserve structure, normalize case
        dex, ticker = symbol.split(":", 1)
        clean_symbol = f"{dex.lower()}:{ticker.upper()}"
    else:
        # Standard perp — strip exchange suffixes and uppercase
        clean_symbol = symbol.split("-")[0].split("/")[0].upper()

    hl_interval  = _hl_interval(interval)
    start_ms, end_ms = _period_to_ms(period) if not (start or end) else (
        int(datetime.fromisoformat(start).timestamp() * 1000) if start else None,
        int(datetime.fromisoformat(end).timestamp()   * 1000) if end else None,
    )

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin":      clean_symbol,
            "interval":  hl_interval,
            "startTime": start_ms,
            "endTime":   end_ms,
        }
    }

    response = requests.post(
        "https://api.hyperliquid.xyz/info",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()
    candles = response.json()

    if not candles:
        return None

    records = []
    for c in candles:
        records.append({
            "date":   datetime.fromtimestamp(c["t"] / 1000, tz=timezone.utc).isoformat(),
            "open":   float(c["o"]),
            "high":   float(c["h"]),
            "low":    float(c["l"]),
            "close":  float(c["c"]),
            "volume": float(c["v"]),
        })

    return records


# ---------------------------------------------------------------------------
# SOURCE: CoinMarketCap
# ---------------------------------------------------------------------------

def _fetch_coinmarketcap(symbol, period, interval, start, end, api_key):
    """
    CoinMarketCap API.
    Requires API key: COINMARKETCAP_KEY in .env or config plugin.

    FREE TIER LIMITATION:
    The free Basic plan does not include historical OHLCV candles.
    This function returns current-price data only on free tier.
    We return a single-candle list (just the latest quote) so the
    plugin's data contract is maintained, but we attach a warning
    in the meta that historical data is unavailable.

    Paid Hobbyist+ tier: full OHLCV historical data via
    /v2/cryptocurrency/ohlcv/historical

    Symbol: use the coin symbol e.g. "BTC", "ETH", "SOL"
    """
    clean_symbol = symbol.split("-")[0].split("/")[0].upper()
    headers      = {"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"}

    # Step 1: Try historical OHLCV (paid tier)
    # If this fails with a 402/403 or plan error, fall back to latest quote.
    if period not in ("1d",):
        try:
            hist_url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/ohlcv/historical"
            count    = {
                "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
                "1y": 365, "2y": 730,
            }.get(period, 30)

            params = {
                "symbol":      clean_symbol,
                "convert":     "USD",
                "time_period": "daily",
                "count":       count,
            }
            r = requests.get(hist_url, headers=headers, params=params, timeout=15)

            if r.status_code == 200:
                data  = r.json()
                coins = data.get("data", {})
                # CMC returns dict keyed by symbol when using symbol param
                if isinstance(coins, dict) and clean_symbol in coins:
                    entries = coins[clean_symbol]
                    if isinstance(entries, list) and entries:
                        coin_data = entries[0]
                    else:
                        coin_data = entries
                    quotes = coin_data.get("quotes", [])
                    records = []
                    for q in quotes:
                        usd = q.get("quote", {}).get("USD", {})
                        records.append({
                            "date":   q.get("time_open", "")[:10],
                            "open":   float(usd.get("open",   0) or 0),
                            "high":   float(usd.get("high",   0) or 0),
                            "low":    float(usd.get("low",    0) or 0),
                            "close":  float(usd.get("close",  0) or 0),
                            "volume": float(usd.get("volume", 0) or 0),
                        })
                    if records:
                        return records

        except Exception:
            pass  # Fall through to latest quote

    # Step 2: Latest quote only (free tier)
    # Returns a single candle with current price for all four OHLC fields.
    # This allows the plugin to return valid data and display the current price,
    # but strategy_engine will not have enough candles to run most indicators.
    quote_url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest"
    params    = {"symbol": clean_symbol, "convert": "USD"}
    r         = requests.get(quote_url, headers=headers, params=params, timeout=15)
    r.raise_for_status()

    data  = r.json()
    coins = data.get("data", {})

    if not coins or clean_symbol not in coins:
        return None

    entries   = coins[clean_symbol]
    coin_data = entries[0] if isinstance(entries, list) else entries
    usd       = coin_data.get("quote", {}).get("USD", {})
    price     = float(usd.get("price", 0) or 0)
    volume    = float(usd.get("volume_24h", 0) or 0)
    now       = datetime.now(timezone.utc).isoformat()

    # Return single-candle list — valid contract but useless for strategies.
    # The meta dict in plugin.py will attach a warning about free tier limits.
    return [{"date": now, "open": price, "high": price,
             "low": price, "close": price, "volume": volume,
             "_cmc_free_tier": True}]



# ---------------------------------------------------------------------------
# SOURCE: Binance
# ---------------------------------------------------------------------------

def _binance_interval(interval: str) -> str:
    """Convert JagDash interval strings to Binance format."""
    mapping = {
        "1m": "1m", "2m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
        "60m": "1h", "90m": "1h", "1h": "1h", "6h": "6h", "12h": "12h",
        "1d": "1d", "3d": "3d", "1wk": "1w", "1mo": "1M",
    }
    mapped = mapping.get(interval)
    if not mapped:
        raise Exception(
            f"Interval '{interval}' not supported by Binance. "
            f"Use: 1m, 3m, 5m, 15m, 30m, 1h, 6h, 12h, 1d, 3d, 1w, 1M"
        )
    return mapped


def _binance_symbol(symbol: str) -> str:
    """
    Normalize any symbol to Binance format (BTCUSDT).

    BTC      → BTCUSDT   (bare coin: append USDT)
    ETH      → ETHUSDT
    BTC-USD  → BTCUSDT   (strip hyphen, replace USD with USDT)
    BTC-USDT → BTCUSDT   (strip hyphen)
    BTCUSDT  → BTCUSDT   (already correct)
    ETHBTC   → ETHBTC     (non-USDT pair: left as-is)

    The key insight: bare coin names like BTC and ETH are 3-4 chars.
    A complete Binance symbol is always longer (BTCUSDT=7, ETHBTC=6).
    We check minimum length to distinguish "BTC" (bare) from "BTCUSDT" (complete).
    """
    sym = symbol.upper().replace("/", "").replace("-", "")

    # Already a complete Binance symbol — must be longer than the longest
    # quote currency (USDT=4 chars) plus at least 2 chars of base coin
    QUOTE_CURRENCIES = ("USDT", "BUSD", "USDC", "BTC", "ETH", "BNB")
    for quote in QUOTE_CURRENCIES:
        if sym.endswith(quote) and len(sym) > len(quote):
            return sym  # already in Binance format

    # Had a USD suffix (from Yahoo-style symbols like BTC-USD → BTCUSD)
    if sym.endswith("USD"):
        return sym[:-3] + "USDT"

    # Bare coin name — default to USDT pair
    return sym + "USDT"


def _fetch_binance(symbol, period, interval, start, end):
    """
    Binance Spot API — public, no key required.
    Endpoint: GET https://api.binance.com/api/v3/klines

    Returns up to 1000 candles per request; auto-paginates for longer ranges.

    Response array positions (Binance docs):
        [0] open time ms, [1] open, [2] high, [3] low, [4] close, [5] volume
    """
    bn_symbol   = _binance_symbol(symbol)
    bn_interval = _binance_interval(interval)

    if start or end:
        start_ms = int(datetime.fromisoformat(start).timestamp() * 1000) if start else None
        end_ms   = int(datetime.fromisoformat(end).timestamp()   * 1000) if end else None
    else:
        start_ms, end_ms = _period_to_ms(period)

    all_candles   = []
    limit         = 1000
    current_start = start_ms

    while True:
        params = {"symbol": bn_symbol, "interval": bn_interval, "limit": limit}
        if current_start:
            params["startTime"] = current_start
        if end_ms:
            params["endTime"] = end_ms

        response = requests.get(
            "https://api.binance.com/api/v3/klines",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        candles = response.json()

        # Binance returns an error dict if the symbol is invalid
        if isinstance(candles, dict) and candles.get("code"):
            raise Exception(
                f"Binance error {candles['code']}: {candles.get('msg', 'unknown')}. "
                f"Symbol tried: {bn_symbol}. "
                f"Use USDT pairs like BTCUSDT, ETHUSDT — or just BTC, ETH."
            )

        if not candles:
            break

        all_candles.extend(candles)

        if len(candles) < limit:
            break  # reached the end

        # Advance past the last candle's close time to avoid overlap
        current_start = int(candles[-1][6]) + 1
        if end_ms and current_start >= end_ms:
            break

    if not all_candles:
        return None

    return [
        {
            "date":   datetime.fromtimestamp(int(c[0]) / 1000,
                                              tz=timezone.utc).isoformat(),
            "open":   float(c[1]),
            "high":   float(c[2]),
            "low":    float(c[3]),
            "close":  float(c[4]),
            "volume": float(c[5]),
        }
        for c in all_candles
    ]

# ---------------------------------------------------------------------------
# SOURCE REGISTRY
# Maps source name → fetch function.
# Adding a new source: add it here. The UI dropdown reads this list.
# ---------------------------------------------------------------------------

def fetch(source: str, symbol: str, period: str, interval: str,
          start=None, end=None, api_key: str = "") -> list[dict] | None:
    """
    Unified fetch dispatcher. Called by market_data plugin.
    Raises Exception on failure — caller handles it.
    Returns None if no data found (valid response but empty).
    """
    if source == "yahoo":
        return _fetch_yfinance(symbol, period, interval, start, end)

    elif source == "hyperliquid":
        return _fetch_hyperliquid(symbol, period, interval, start, end)

    elif source == "binance":
        return _fetch_binance(symbol, period, interval, start, end)

    elif source == "coinmarketcap":
        if not api_key:
            raise Exception(
                "CoinMarketCap requires an API key. "
                "Add COINMARKETCAP_KEY to your .env file or config plugin."
            )
        return _fetch_coinmarketcap(symbol, period, interval, start, end, api_key)

    else:
        raise Exception(f"Unknown data source: '{source}'. "
                        f"Available: yahoo, hyperliquid, coinmarketcap")


# Source display names for the UI dropdown
SOURCE_LABELS = {
    "yahoo":         "Yahoo Finance",
    "hyperliquid":   "Hyperliquid (no key needed)",
    "binance":       "Binance (no key needed)",
    "coinmarketcap": "CoinMarketCap (API key required)",
}

SOURCE_NOTES = {
    "yahoo": "Stocks, ETFs, crypto (BTC-USD format), forex, futures.",
    "hyperliquid": (
        "Perpetual futures only. No API key required. Up to 5000 candles. "
        "Standard perps: BTC, ETH, SOL. "
        "HIP-3 real-world assets: xyz:BRENTOIL, xyz:GOLD, xyz:CL (WTI oil). "
        "Use lowercase dex prefix: xyz:TICKER."
    ),
    "binance": (
        "Spot pairs, no API key required. Auto-paginates for long ranges. "
        "Use USDT pairs: BTCUSDT, ETHUSDT — or just BTC, ETH (USDT assumed). "
        "Not available in all countries (US users: try Binance.US)."
    ),
    "coinmarketcap": (
        "Free tier: current price only (1 candle). "
        "Historical OHLCV candles require a paid Hobbyist plan or higher. "
        "Use coin symbol: BTC, ETH, SOL."
    ),
}

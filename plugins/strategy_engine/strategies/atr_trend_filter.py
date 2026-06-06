# strategies/atr_trend_filter.py
# ATR-Filtered EMA Trend Strategy
#
# Why Python instead of YAML:
#   The volatility gate requires comparing ATR to a moving average OF ATR.
#   The YAML engine applies indicators to the close price series only.
#   SMA-of-ATR requires a two-step computation (compute ATR first, then smooth it)
#   which the declarative engine can't express. Python handles this cleanly.

import pandas as pd


def manifest() -> dict:
    return {
        "name":        "ATR Trend Filter",
        "type":        "Trend-following / Volatility-gated",
        "description": (
            "EMA(9)/EMA(21) crossover gated by an ATR volatility filter. "
            "Only signals BUY or SELL when the 14-period ATR is above its own "
            "10-period moving average — meaning volatility is expanding and a "
            "trend is likely developing. Returns HOLD during quiet, sideways "
            "conditions where EMA crossovers produce frequent false signals. "
            "Addresses a key weakness of pure trend-following: noise filtering. "
            "Most useful on intraday charts (5m–1h) where chop is common. "
            "Pairs naturally with the built-in EMA Crossover strategy: that one "
            "fires freely, this one only fires when market conditions support it."
        ),
        "min_candles": 70,
    }


def signal(df: pd.DataFrame) -> str:
    """
    Logic:
      1. EMA(9) vs EMA(21) — direction
      2. ATR(14) vs EMA(10) of ATR(14) — is volatility expanding?
      3. Only emit BUY/SELL when both agree. Otherwise HOLD.

    The ATR gate is the key innovation over plain EMA crossover.
    When ATR > its own moving average, recent bars are moving more than
    usual — suggesting a trend is developing rather than random chop.
    When ATR < its moving average, the market is quiet — crossovers here
    are unreliable and we stay out.
    """
    close = df["close"]

    ema_fast = close.ewm(span=9,  adjust=False).mean()
    ema_slow = close.ewm(span=21, adjust=False).mean()

    # ATR approximation using close-to-close (no OHLC needed)
    # True ATR uses high-low range; this approximation works on close-only data
    # which is what market.price guarantees across all intervals.
    atr      = close.diff().abs().rolling(14).mean()
    atr_ema  = atr.ewm(span=10, adjust=False).mean()

    fast     = ema_fast.iloc[-1]
    slow     = ema_slow.iloc[-1]
    atr_now  = atr.iloc[-1]
    atr_base = atr_ema.iloc[-1]

    # Bail out if any indicator hasn't warmed up yet
    if any(pd.isna(v) for v in [fast, slow, atr_now, atr_base]):
        return "HOLD"

    # Volatility gate: is the market moving more than its recent baseline?
    trending = atr_now > atr_base

    if not trending:
        # Market is quiet — EMA crossover signals here are unreliable
        return "HOLD"

    if fast > slow:
        return "BUY"
    if fast < slow:
        return "SELL"
    return "HOLD"

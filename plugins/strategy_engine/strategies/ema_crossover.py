# strategies/ema_crossover.py
# Example external Python strategy — NiteTrader / JagDash Strategy Engine
#
# Use this as a template for Python strategies that need logic
# beyond what the YAML format can express.

import pandas as pd


def manifest() -> dict:
    return {
        "name":        "EMA Crossover",
        "type":        "Momentum / Trend-following",
        "description": (
            "Fast EMA(9) vs Slow EMA(21) crossover. "
            "Exponential moving averages weight recent prices more heavily than SMAs, "
            "so this reacts faster to trend changes than the built-in SMA Crossover. "
            "The trade-off: more responsive to real turns, but also more prone to "
            "whipsaws in choppy sideways conditions. "
            "Pairs well with a volatility filter to reduce false signals."
        ),
        "min_candles": 30,
    }


def signal(df: pd.DataFrame) -> str:
    close    = df["close"]
    ema_fast = close.ewm(span=9,  adjust=False).mean()
    ema_slow = close.ewm(span=21, adjust=False).mean()

    fast = ema_fast.iloc[-1]
    slow = ema_slow.iloc[-1]

    if pd.isna(fast) or pd.isna(slow):
        return "HOLD"

    if fast > slow:  return "BUY"
    if fast < slow:  return "SELL"
    return "HOLD"

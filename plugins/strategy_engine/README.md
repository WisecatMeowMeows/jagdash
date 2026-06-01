# strategies/README.md
# NiteTrader — External Strategy Reference

Drop a file in this directory. The Strategy Engine auto-discovers it on
startup and when you click **🔄 Reload Strategies** in the UI.

Files starting with `_` are skipped (`__init__.py`, `_helpers.py`, etc.).

---

## Two formats

### 1. YAML / JSON — for traders, no coding required

Write a `.yaml` (or `.json`) file. No Python needed.

```yaml
name: "My Strategy"
description: "What it does and why."

indicators:
  rsi:    { type: rsi, period: 14 }
  ema_50: { type: ema, period: 50 }
  close:  { type: close }

rules:
  - signal: BUY
    when:
      all:
        - [rsi,   "<", 35]
        - [close, ">", ema_50]

  - signal: SELL
    when: [rsi, ">", 65]

  - signal: HOLD
    default: true
```

See `rsi_ema_filter.yaml` for a fully commented example.

---

### 2. Python — for developers needing custom logic

```python
def manifest() -> dict:
    return {
        "name":        "My Strategy",     # unique display name
        "description": "One-liner.",
        "type":        "Trend-following", # shown in info popover
        "min_candles": 50,                # informational
    }

def signal(df: pd.DataFrame) -> str:
    # your logic here
    return "HOLD"   # BUY | SELL | HOLD | WATCH
```

See `ema_crossover.py` for a working example.

---

## YAML — indicator reference

```yaml
indicators:
  my_rsi:         { type: rsi,          period: 14 }
  fast_ema:       { type: ema,          period: 9  }
  slow_sma:       { type: sma,          period: 50 }
  macd_line:      { type: macd,         fast: 12, slow: 26 }
  macd_sig:       { type: macd_signal,  fast: 12, slow: 26, signal_period: 9 }
  upper_band:     { type: bb_upper,     period: 20, std: 2.0 }
  lower_band:     { type: bb_lower,     period: 20, std: 2.0 }
  middle_band:    { type: bb_mid,       period: 20 }
  high_20:        { type: rolling_high, period: 20 }
  low_20:         { type: rolling_low,  period: 20 }
  atr_14:         { type: atr,          period: 14 }
  current_close:  { type: close }
  current_volume: { type: volume }        # NaN if market.price omits volume
```

All parameters have sensible defaults; you only need to specify what differs.

---

## YAML — rules reference

Rules are evaluated **top to bottom**. First match wins. Always include
a `default: true` rule at the bottom as a catch-all.

### Single condition
```yaml
when: [variable, operator, value_or_variable]
```

### AND — all conditions must be true
```yaml
when:
  all:
    - [rsi, "<", 30]
    - [close, ">", ema_50]
```

### OR — at least one condition must be true
```yaml
when:
  any:
    - [rsi, ">", 70]
    - [close, "<", ema_50]
```

### Operators
`<`  `>`  `<=`  `>=`  `==`  `!=`

### Right-hand side
- A **number**: `[rsi, "<", 30]`
- Another **indicator name**: `[close, ">", ema_50]` — both sides are variables

---

## Valid signal strings

| Signal  | Meaning                              |
|---------|--------------------------------------|
| `BUY`   | Bullish — price expected to rise     |
| `SELL`  | Bearish — price expected to fall     |
| `HOLD`  | Neutral / no edge detected           |
| `WATCH` | Setup forming, direction unclear     |

**Only these four strings.** Anything else is silently treated as `HOLD`.

---

## Rules for both formats

- **Never raise an exception.** Return `HOLD` on error.
- `df` always has a `close` column. Other columns (`open`, `high`, `low`,
  `volume`) may or may not be present — check before using.
- **Do not** import other plugin files.
- **Do not** use `st.*` in strategy functions (runs headless).
- **Do not** store mutable global state — one instance serves all sessions.

---

## What YAML can't do (use Python instead)

- Multi-bar lookback: "RSI crossed below 30 in the last 3 bars"
- Math between indicators: `(ema_fast - ema_slow) / atr`
- Stateful logic that remembers previous bars
- Conditional indicator parameters

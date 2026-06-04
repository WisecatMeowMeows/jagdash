# strategy_engine.py
# JagDash Strategy Engine Plugin v1.3
# NiteTrader Plugin Ecosystem
#
# Provides: market.strategy.signal
# Requires: market.price
#
# v1.3 changes:
#   - Info popovers (ℹ) with per-strategy descriptions in the UI
#   - YAML/JSON declarative strategy support in strategies/ subdirectory
#   - Unified strategy metadata (description, source, type) across all strategies

import importlib.util
import pandas as pd
import numpy as np

from pathlib import Path

# yaml is imported lazily inside _load_declarative_file() so that:
#   (a) a missing PyYAML doesn't prevent the plugin from loading at all
#   (b) clicking "Reload Strategies" after installing PyYAML works without
#       restarting the Streamlit server


PLUGIN_NAME    = "Strategy Engine"
STRATEGIES_DIR = Path(__file__).parent / "strategies"


# ============================================================
# SIGNAL VOCABULARY  (per JagDash spec)
# ============================================================

SIGNAL_SCORES: dict[str, float] = {
    "BUY":   1.0,
    "SELL": -1.0,
    "HOLD":  0.0,
    "WATCH": 0.0,
}

BUY_THRESHOLD  =  0.25
SELL_THRESHOLD = -0.25
DEFAULT_WEIGHT = 1.0


# ============================================================
# MANIFEST
# ============================================================

def manifest() -> dict:
    return {
        "name":     "strategy_engine",
        "version":  "1.3",
        "provides": ["market.strategy.signal"],
        "requires": ["market.price"],
    }

# ============================================================
# GET UI CONTEXT
# ============================================================

def get_ui_context(context):
    """Return data needed by partials/strategy_engine.html"""
    strategy_list = []
    for name in STRATEGIES:
        meta = _strategy_meta.get(name, {})
        strategy_list.append({
            "name": name,
            "type": meta.get("type", ""),
            "description": meta.get("description", ""),
            "source": meta.get("source", "built-in"),
            "min_candles": meta.get("min_candles", 0),
            "file": meta.get("file", ""),
        })
    return {
        "strategies": strategy_list,
        "interval_options": ["1m","2m","5m","15m","30m","60m","90m","1h","1d","1wk","1mo"],
        "period_options": ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"],
        "errors": _discovery_errors,
    }
# ============================================================
# INDICATORS
# Stateless; always operate on a copy of the series.
# ============================================================

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.where(delta > 0, 0.0).rolling(period).mean()
    loss  = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema12  = series.ewm(span=12, adjust=False).mean()
    ema26  = series.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


# ============================================================
# BUILT-IN STRATEGY FUNCTIONS
# Contract: f(df: pd.DataFrame) -> str
# ============================================================

def sma_crossover(df: pd.DataFrame) -> str:
    df["sma_fast"] = df["close"].rolling(20).mean()
    df["sma_slow"] = df["close"].rolling(50).mean()
    latest = df.iloc[-1]
    if pd.isna(latest["sma_fast"]) or pd.isna(latest["sma_slow"]): return "HOLD"
    if latest["sma_fast"] > latest["sma_slow"]: return "BUY"
    if latest["sma_fast"] < latest["sma_slow"]: return "SELL"
    return "HOLD"


def rsi_mean_reversion(df: pd.DataFrame) -> str:
    rsi = calculate_rsi(df["close"])
    v   = rsi.iloc[-1]
    if pd.isna(v): return "HOLD"
    if v < 30: return "BUY"
    if v > 70: return "SELL"
    return "HOLD"


def macd_trend(df: pd.DataFrame) -> str:
    df["macd"], df["macd_sig"] = calculate_macd(df["close"])
    latest = df.iloc[-1]
    if pd.isna(latest["macd"]) or pd.isna(latest["macd_sig"]): return "HOLD"
    if latest["macd"] > latest["macd_sig"]: return "BUY"
    if latest["macd"] < latest["macd_sig"]: return "SELL"
    return "HOLD"


def breakout_momentum(df: pd.DataFrame) -> str:
    high_20 = df["close"].rolling(20).max().iloc[-1]
    low_20  = df["close"].rolling(20).min().iloc[-1]
    current = df.iloc[-1]["close"]
    if pd.isna(high_20) or pd.isna(low_20): return "HOLD"
    if current >= high_20: return "BUY"
    if current <= low_20:  return "SELL"
    return "HOLD"


def volatility_squeeze(df: pd.DataFrame) -> str:
    close    = df["close"]
    bb_mid   = close.rolling(20).mean()
    bb_std   = close.rolling(20).std()
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std
    c_atr    = close.diff().abs().rolling(20).mean()
    kc_upper = bb_mid + 1.5 * c_atr
    kc_lower = bb_mid - 1.5 * c_atr

    vals = [bb_upper.iloc[-1], bb_lower.iloc[-1],
            kc_upper.iloc[-1], kc_lower.iloc[-1]]
    if any(pd.isna(v) for v in vals): return "HOLD"

    squeeze = (bb_upper.iloc[-1] < kc_upper.iloc[-1]) and \
              (bb_lower.iloc[-1] > kc_lower.iloc[-1])
    if not squeeze: return "HOLD"

    rsi = calculate_rsi(close).iloc[-1]
    if pd.isna(rsi):  return "WATCH"
    if rsi > 55:      return "BUY"
    if rsi < 45:      return "SELL"
    return "WATCH"


# ============================================================
# BUILT-IN METADATA
# Descriptions shown in the ℹ popover for each built-in strategy.
# ============================================================

BUILTIN_META: dict[str, dict] = {
    "SMA Crossover": {
        "description": (
            "Compares a fast 20-period simple moving average against a slow 50-period SMA. "
            "When the fast line is above the slow line, short-term price momentum is stronger "
            "than the longer trend → BUY. Classic trend-following logic: simple, robust, and "
            "lagging by nature. Works well in sustained trends; gives many false signals in "
            "choppy sideways markets."
        ),
        "type":        "Trend-following",
        "min_candles": 50,
    },
    "RSI Mean Reversion": {
        "description": (
            "Uses the 14-period Relative Strength Index. RSI measures how fast and far price "
            "has moved recently on a 0–100 scale. Below 30 = oversold (exhausted sellers) → BUY. "
            "Above 70 = overbought (exhausted buyers) → SELL. Counter-trend logic — it deliberately "
            "fights momentum, betting on a snap-back. Conflicts with SMA/MACD on purpose; "
            "that conflict is useful signal."
        ),
        "type":        "Mean-reversion / Counter-trend",
        "min_candles": 28,
    },
    "MACD Trend": {
        "description": (
            "MACD (Moving Average Convergence/Divergence) subtracts a 26-period EMA from a "
            "12-period EMA to produce the MACD line, then smooths that with a 9-period EMA "
            "called the signal line. When MACD is above its signal line, upward momentum is "
            "accelerating → BUY. Reacts faster than SMA Crossover, still lags at reversals. "
            "EMA weighting makes it more responsive to recent price action than pure SMAs."
        ),
        "type":        "Momentum / Trend-following",
        "min_candles": 35,
    },
    "Breakout Momentum": {
        "description": (
            "Pure price action — no indicator math. Checks whether today's close is at the "
            "highest or lowest point of the last 20 bars. New 20-bar high = price is breaking "
            "out of its recent range upward → BUY. New 20-bar low = breaking down → SELL. "
            "Zero lag (no smoothing), so it reacts immediately but is prone to false breakouts "
            "in low-volatility chop. Pairs well with a volatility filter."
        ),
        "type":        "Price action / Breakout",
        "min_candles": 20,
    },
    "Volatility Squeeze": {
        "description": (
            "Detects when Bollinger Bands compress inside Keltner Channels — a sign that "
            "volatility is contracting and a breakout is likely building. Think of it like "
            "a spring being wound: the squeeze is the tension, not the direction. "
            "When the squeeze is active, RSI bias picks the expected direction (BUY/SELL); "
            "if RSI is neutral, returns WATCH. When no squeeze, returns HOLD. "
            "Uses a close-only ATR approximation (no OHLCV required)."
        ),
        "type":        "Volatility / Setup detection",
        "min_candles": 30,
    },
}


# ============================================================
# BUILT-IN STRATEGY REGISTRY
# ============================================================

BUILTIN_STRATEGIES: dict[str, callable] = {
    "SMA Crossover":       sma_crossover,
    "RSI Mean Reversion":  rsi_mean_reversion,
    "MACD Trend":          macd_trend,
    "Breakout Momentum":   breakout_momentum,
    "Volatility Squeeze":  volatility_squeeze,
}


# ============================================================
# DECLARATIVE (YAML/JSON) STRATEGY ENGINE
# Compiles a config dict → signal(df) callable.
# ============================================================

def _build_indicator_value(
    df: pd.DataFrame, itype: str, params: dict
) -> float:
    """Compute one scalar indicator value from the dataframe's close series."""
    close = df["close"]

    if itype == "close":
        return float(close.iloc[-1])

    elif itype == "sma":
        period = int(params.get("period", 20))
        return float(close.rolling(period).mean().iloc[-1])

    elif itype == "ema":
        period = int(params.get("period", 20))
        return float(close.ewm(span=period, adjust=False).mean().iloc[-1])

    elif itype == "rsi":
        period = int(params.get("period", 14))
        return float(calculate_rsi(close, period).iloc[-1])

    elif itype == "macd":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        return float(
            (close.ewm(span=fast, adjust=False).mean()
             - close.ewm(span=slow, adjust=False).mean()).iloc[-1]
        )

    elif itype == "macd_signal":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        sig  = int(params.get("signal_period", 9))
        macd_line = (close.ewm(span=fast, adjust=False).mean()
                     - close.ewm(span=slow, adjust=False).mean())
        return float(macd_line.ewm(span=sig, adjust=False).mean().iloc[-1])

    elif itype == "bb_upper":
        period = int(params.get("period", 20))
        std    = float(params.get("std", 2.0))
        return float((close.rolling(period).mean()
                      + std * close.rolling(period).std()).iloc[-1])

    elif itype == "bb_lower":
        period = int(params.get("period", 20))
        std    = float(params.get("std", 2.0))
        return float((close.rolling(period).mean()
                      - std * close.rolling(period).std()).iloc[-1])

    elif itype == "bb_mid":
        period = int(params.get("period", 20))
        return float(close.rolling(period).mean().iloc[-1])

    elif itype == "rolling_high":
        period = int(params.get("period", 20))
        return float(close.rolling(period).max().iloc[-1])

    elif itype == "rolling_low":
        period = int(params.get("period", 20))
        return float(close.rolling(period).min().iloc[-1])

    elif itype == "atr":
        period = int(params.get("period", 14))
        return float(close.diff().abs().rolling(period).mean().iloc[-1])

    elif itype == "volume":
        if "volume" in df.columns:
            return float(df["volume"].iloc[-1])
        return float("nan")

    return float("nan")


_CONDITION_OPS: dict[str, callable] = {
    "<":  lambda a, b: a < b,
    ">":  lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _eval_condition(cond: list, values: dict[str, float]) -> bool:
    """
    Evaluate a single condition: [left_var, operator, right_var_or_literal].
    Returns False if either operand is NaN or the operator is unrecognised.
    """
    if not isinstance(cond, list) or len(cond) != 3:
        return False

    left_name, op_str, right = cond
    left_val = values.get(str(left_name), float("nan"))

    right_val = values.get(str(right), float("nan")) \
                if isinstance(right, str) \
                else float(right)

    if pd.isna(left_val) or pd.isna(right_val):
        return False

    op_fn = _CONDITION_OPS.get(str(op_str))
    return bool(op_fn(left_val, right_val)) if op_fn else False


def _eval_when(when, values: dict[str, float]) -> bool:
    """
    Evaluate a `when` block. Supports:
      - Single condition:  [var, op, val]
      - all: [...]         every condition must be true (AND)
      - any: [...]         at least one condition must be true (OR)
    """
    if isinstance(when, list):
        return _eval_condition(when, values)

    if isinstance(when, dict):
        if "all" in when:
            return all(_eval_condition(c, values) for c in when["all"])
        if "any" in when:
            return any(_eval_condition(c, values) for c in when["any"])

    return False


def _make_declarative_signal_fn(config: dict) -> callable:
    """
    Compile a YAML/JSON config dict into a signal(df) -> str callable.
    The returned function is self-contained and follows the standard strategy contract.
    """
    indicators_cfg: dict = config.get("indicators", {})
    rules: list          = config.get("rules", [])

    def signal(df: pd.DataFrame) -> str:
        try:
            # Step 1: compute all declared indicator values
            values: dict[str, float] = {}
            for var_name, cfg in indicators_cfg.items():
                if isinstance(cfg, dict):
                    itype  = cfg.get("type", var_name)
                    params = cfg
                else:
                    itype  = str(cfg)
                    params = {}
                values[var_name] = _build_indicator_value(df, itype, params)

            # Step 2: evaluate rules top-to-bottom; return first match
            for rule in rules:
                if rule.get("default"):
                    return str(rule.get("signal", "HOLD")).upper()
                when = rule.get("when")
                if when is not None and _eval_when(when, values):
                    sig = str(rule.get("signal", "HOLD")).upper()
                    return sig if sig in SIGNAL_SCORES else "HOLD"

        except Exception:
            pass    # any unexpected failure → safe fallback

        return "HOLD"

    return signal


def _load_declarative_file(path: Path) -> tuple[dict | None, str | None]:
    """
    Parse a .yaml / .yml / .json strategy file.
    Returns (config_dict, None) on success, (None, error_message) on failure.

    yaml is imported here (not at module level) so that:
    - A missing PyYAML doesn't prevent the plugin from loading.
    - Installing PyYAML then clicking Reload Strategies works without
      a full Streamlit server restart (module-level flags don't re-evaluate).
    """
    try:
        import yaml
    except ImportError:
        return None, "PyYAML not installed — run: python -m pip install pyyaml"

    try:
        text = path.read_text(encoding="utf-8")
        config = yaml.safe_load(text)   # safe_load also handles JSON
    except Exception as e:
        return None, f"Parse error: {e}"

    if not isinstance(config, dict):
        return None, "Top-level structure must be a YAML mapping (key: value)"

    if "rules" not in config:
        return None, "Missing required 'rules' list"

    return config, None


# ============================================================
# EXTERNAL STRATEGY DISCOVERY  (Python + YAML/JSON)
# ============================================================

def _discover_external_strategies(
    directory: Path,
) -> tuple[dict[str, callable], dict[str, dict], dict[str, str]]:
    """
    Scan `directory` for .py and .yaml/.yml/.json strategy files.
    Files starting with _ are skipped.

    Returns:
        discovered : {display_name: signal_fn}
        meta       : {display_name: {description, source, type, ...}}
        errors     : {filename: error_message}
    """
    discovered: dict[str, callable] = {}
    meta:       dict[str, dict]     = {}
    errors:     dict[str, str]      = {}

    if not directory.is_dir():
        return discovered, meta, errors

    # Collect all candidate files: .py, .yaml, .yml, .json
    candidates = sorted(
        p for p in directory.iterdir()
        if p.suffix in {".py", ".yaml", ".yml", ".json"}
        and not p.name.startswith("_")
    )

    for path in candidates:
        # ---- Python strategy ----------------------------------------
        if path.suffix == ".py":
            module_id = f"_jagdash_ext_{path.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_id, path)
                if spec is None or spec.loader is None:
                    errors[path.name] = "importlib could not read file"
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                if not hasattr(module, "signal") or not callable(module.signal):
                    errors[path.name] = "Missing or non-callable signal(df) function"
                    continue

                # Resolve name + description from optional manifest()
                if hasattr(module, "manifest") and callable(module.manifest):
                    try:
                        m    = module.manifest()
                        name = m.get("name") or path.stem.replace("_", " ").title()
                        desc = m.get("description", "")
                        mtype = m.get("type", "External / Python")
                    except Exception as e:
                        name  = path.stem.replace("_", " ").title()
                        desc  = ""
                        mtype = "External / Python"
                        errors[path.name] = f"manifest() raised: {e}"
                else:
                    name  = path.stem.replace("_", " ").title()
                    desc  = ""
                    mtype = "External / Python"

                if name in BUILTIN_STRATEGIES:
                    errors[path.name] = f"Note: '{name}' overrides a built-in strategy"

                discovered[name] = module.signal
                meta[name] = {
                    "description": desc,
                    "type":        mtype,
                    "source":      "external-python",
                    "file":        path.name,
                    "min_candles": int(m.get("min_candles", 0)) if hasattr(module, "manifest") else 0,
                }

            except Exception as e:
                errors[path.name] = f"Load error: {e}"

        # ---- Declarative (YAML / JSON) strategy ---------------------
        elif path.suffix in {".yaml", ".yml", ".json"}:
            config, err = _load_declarative_file(path)
            if err:
                errors[path.name] = err
                continue

            name  = config.get("name") or path.stem.replace("_", " ").title()
            desc  = config.get("description", "").strip()
            mtype = config.get("type", "External / Declarative")

            if name in BUILTIN_STRATEGIES:
                errors[path.name] = f"Note: '{name}' overrides a built-in strategy"

            try:
                fn = _make_declarative_signal_fn(config)
            except Exception as e:
                errors[path.name] = f"Compile error: {e}"
                continue

            discovered[name] = fn
            meta[name] = {
                "description": desc,
                "type":        mtype,
                "source":      "external-declarative",
                "file":        path.name,
                "indicators":  list(config.get("indicators", {}).keys()),
                "min_candles": int(config.get("min_candles", 0)),
            }

    return discovered, meta, errors


# ============================================================
# ACTIVE STRATEGY TABLE  (built-ins + external)
# ============================================================

STRATEGIES:        dict[str, callable] = dict(BUILTIN_STRATEGIES)
_strategy_meta:    dict[str, dict]     = dict(BUILTIN_META)
_discovery_errors: dict[str, str]      = {}
_external_names:   set[str]            = set()


def _reload_strategies() -> None:
    """Rescan strategies/ and rebuild the merged STRATEGIES table."""
    global STRATEGIES, _strategy_meta, _discovery_errors, _external_names

    external, ext_meta, errors = _discover_external_strategies(STRATEGIES_DIR)

    _discovery_errors = errors
    _external_names   = set(external.keys())

    # Merge: built-ins first, external on top (external wins on collision)
    STRATEGIES     = {**BUILTIN_STRATEGIES, **external}
    _strategy_meta = {**BUILTIN_META, **ext_meta}


_reload_strategies()


# ============================================================
# COMBINED SIGNAL LOGIC
# ============================================================

def compute_combined_signal(
    results: dict[str, str],
    weights: dict[str, float],
) -> dict:
    weighted_score = 0.0
    total_weight   = 0.0

    for name, sig in results.items():
        w = weights.get(name, DEFAULT_WEIGHT)
        if w <= 0.0: continue
        weighted_score += w * SIGNAL_SCORES.get(sig, 0.0)
        total_weight   += w

    if total_weight == 0.0:
        return {"signal": "HOLD", "score": 0.0, "confidence": 0.0}

    normalized = weighted_score / total_weight

    if normalized >= BUY_THRESHOLD:   combined = "BUY"
    elif normalized <= SELL_THRESHOLD: combined = "SELL"
    else:                              combined = "HOLD"

    return {
        "signal":     combined,
        "score":      round(normalized, 4),
        "confidence": round(min(abs(normalized), 1.0) * 100.0, 1),
    }


# ============================================================
# MARKET DATA NORMALIZER
# ============================================================

def _normalize_market_data(
    market_data,
) -> tuple[pd.DataFrame | None, str | None]:
    if isinstance(market_data, list):
        df = pd.DataFrame(market_data)
    elif isinstance(market_data, dict):
        if "historical" in market_data:
            df = pd.DataFrame(market_data["historical"])
        elif "close" in market_data:
            df = pd.DataFrame([market_data])
        elif "price" in market_data:
            df = pd.DataFrame([{"close": market_data["price"]}])
        else:
            return None, "Unsupported market data format"
    else:
        return None, f"Invalid market data type: {type(market_data)}"

    if df.empty:                    return None, "Market dataframe is empty"
    if "close" not in df.columns:  return None, "Missing required 'close' column"

    # Absolute floor: 3 rows lets diff() and rolling(2) produce at least one
    # non-NaN value. Beyond this, strategies self-manage — insufficient data
    # for an indicator returns NaN, NaN conditions fail, default HOLD fires.
    # No higher global gate; each strategy declares its own min_candles.
    if len(df) < 3:
        return None, f"Market data too short: {len(df)} candle(s); need at least 3"

    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    if df["close"].isna().all():   return None, "All 'close' values are non-numeric"

    return df, None



# ============================================================
# MARKET METADATA EXTRACTOR
#
# Works in two modes:
#   NOW  — infers what it can from the raw dataframe (candle count,
#           available columns, date range if timestamps are present,
#           last price and price range).
#   FUTURE — if market.price starts returning a top-level "meta" dict
#           alongside "data", those fields are used directly and take
#           precedence.  No changes needed here when that upgrade lands.
#
# Fields market_data should provide in its "meta" dict (spec for upgrade):
#   interval   : str   — "1d" | "1h" | "5m" | ...
#   source     : str   — "yfinance" | "alpaca" | ...
#   asset_class: str   — "crypto" | "equity" | "forex" | ...
#   currency   : str   — "USD" | "EUR" | ...
#   date_from  : str   — ISO-8601 first candle timestamp
#   date_to    : str   — ISO-8601 last candle timestamp
# ============================================================

def _infer_period_string(candle_count: int, interval: str) -> tuple[str, bool]:
    """
    Convert (candle_count, interval) → (human-readable span, is_estimated).

    is_estimated is True when the interval was assumed rather than provided.

    Two calculation paths:
    - INTRADAY ("1m".."1h"): use trading-session minutes (390 min/day).
    - DAILY / WEEKLY / MONTHLY: use calendar units.
      "1d" uses 365.25 calendar days/year rather than 252 trading days.
      This is accurate for 24/7 assets (crypto) and a reasonable approximation
      for traditional markets; the old 252-day divisor was badly wrong for crypto
      (5 years of BTC daily data showed as 7.25 years).
    """
    INTRADAY_MINUTES: dict[str, int] = {
        "1m": 1, "2m": 2, "5m": 5, "15m": 15,
        "30m": 30, "60m": 60, "90m": 90, "1h": 60,
    }

    assumed = (interval not in INTRADAY_MINUTES
               and interval not in {"1d", "1wk", "1mo"})

    # ── Daily / weekly / monthly: calendar-unit math ─────────────────
    if interval == "1d" or (assumed):            # unknown → assume daily
        days = candle_count
        if days < 14:
            return f"~{days} days", assumed
        elif days < 60:
            return f"~{days / 7:.1f} wk", assumed
        elif days < 365:
            return f"~{days / 30.44:.1f} mo", assumed
        else:
            return f"~{days / 365.25:.2f} yr", assumed

    if interval == "1wk":
        weeks = candle_count
        if weeks < 8:
            return f"~{weeks} wk", False
        elif weeks < 52:
            return f"~{weeks / 4.33:.1f} mo", False
        else:
            return f"~{weeks / 52:.2f} yr", False

    if interval == "1mo":
        months = candle_count
        if months < 12:
            return f"~{months} mo", False
        else:
            return f"~{months / 12:.1f} yr", False

    # ── Intraday: trading-session-minute math ─────────────────────────
    total_minutes = candle_count * INTRADAY_MINUTES[interval]

    if total_minutes < 120:
        return f"~{int(total_minutes)} min", False
    elif total_minutes <= 60 * 48:
        return f"~{total_minutes / 60:.1f} hr", False
    elif total_minutes < 390 * 15:
        return f"~{total_minutes / 390:.0f} trading days", False
    elif total_minutes < 390 * 63:
        return f"~{total_minutes / (390 * 5):.1f} wk", False
    elif total_minutes < 390 * 252:
        return f"~{total_minutes / (390 * 21):.1f} mo", False
    else:
        return f"~{total_minutes / (390 * 252):.2f} yr", False



def _extract_market_meta(
    market_response: dict,
    df: pd.DataFrame,
    symbol: str,
) -> dict:
    """
    Build a display-ready metadata dict from the market.price response.
    Always includes inferred fields; merges in any provided meta fields.
    """
    meta: dict = {}

    # --- Merge explicitly provided metadata (from market_data's meta dict) ---
    provided = market_response.get("meta") or {}

    # Symbol — always known from the request
    meta["symbol"] = symbol

    # Candle count — prefer authoritative value from market_data
    meta["candle_count"] = provided.get("candles", len(df))

    # Interval — provided by market_data; fall back to "1d"
    meta["interval"] = provided.get("interval", "1d")

    # Columns — market_data gives us the real list from records[0].keys();
    # this is more authoritative than inferring from df.columns
    meta["columns"] = provided.get("columns") or sorted(df.columns.tolist())

    # --- Price snapshot (always inferred from the dataframe) ---
    close = df["close"].dropna()
    if not close.empty:
        meta["price_last"] = round(float(close.iloc[-1]), 6)
        meta["price_min"]  = round(float(close.min()),    6)
        meta["price_max"]  = round(float(close.max()),    6)

    # --- Source, asset class, currency (present only when market_data provides) ---
    for key in ("source", "asset_class", "currency"):
        if key in provided:
            meta[key] = provided[key]

    # --- Time period display ---
    # Priority order:
    #   1. Explicit date range (start + end) — most precise
    #   2. yfinance period string ("6mo", "5y") — exact, user-chosen
    #   3. Inferred from candle count — fallback when neither is available
    start_date = provided.get("start")
    end_date   = provided.get("end")

    if start_date and end_date:
        meta["period_str"]       = f"{start_date}  →  {end_date}"
        meta["period_estimated"] = False

    elif provided.get("period"):
        # Use the yfinance period string directly — it's what was requested
        meta["period_str"]       = provided["period"]
        meta["period_estimated"] = False

    else:
        # Nothing provided — infer from candle count and interval
        span, unrecognized = _infer_period_string(
            meta["candle_count"], meta["interval"]
        )
        meta["period_str"]       = span
        meta["period_estimated"] = True   # genuinely unknown

    return meta

# ============================================================
# HANDLE REQUEST
# ============================================================

def handle_request(request: dict, context) -> dict:
    capability = request.get("capability")
    payload    = request.get("payload", {})

    if capability != "market.strategy.signal":
        return {"status": "error", "message": f"Unsupported capability: {capability}"}

    symbol   = payload.get("symbol",   "BTC-USD")
    interval = payload.get("interval", "1d")
    period   = payload.get("period",   "6mo")
    selected = payload.get("strategies", list(STRATEGIES.keys()))
    weights  = payload.get("weights", {n: DEFAULT_WEIGHT for n in selected})

    unknown = [s for s in selected if s not in STRATEGIES]
    if unknown:
        return {"status": "error", "message": f"Unknown strategy name(s): {unknown}"}
    if not selected:
        return {"status": "error", "message": "No strategies selected"}

    try:
        market_response = context.request(
            "market.price",
            {"symbol": symbol, "interval": interval, "period": period},
        )
    except Exception as e:
        return {"status": "error", "message": f"market.price raised: {e}"}

    if market_response["status"] != "success":
        return market_response

    df, err = _normalize_market_data(market_response.get("data"))
    if err:
        return {"status": "error", "message": err}

    individual_results: dict[str, str] = {}
    strategy_errors:    dict[str, str] = {}

    n_candles = len(df)

    for name in selected:
        # Respect per-strategy minimum candle requirement if declared.
        # Strategies that can't compute return HOLD via NaN propagation anyway,
        # but surfacing the reason is more useful than a silent HOLD.
        min_c = _strategy_meta.get(name, {}).get("min_candles", 0)
        if min_c and n_candles < min_c:
            individual_results[name] = "HOLD"
            strategy_errors[name] = (
                f"Needs ≥{min_c} candles; got {n_candles} — returning HOLD"
            )
            continue
        try:
            individual_results[name] = STRATEGIES[name](df.copy())
        except Exception as e:
            individual_results[name] = "HOLD"
            strategy_errors[name]    = str(e)

    combined = compute_combined_signal(individual_results, weights)

    context.publish(
        "strategy.signal.generated",
        {"symbol": symbol, "strategy": "combined", "signal": combined["signal"]},
    )

    market_meta = _extract_market_meta(market_response, df, symbol)

    return {
        "status": "success",
        "data": {
            "symbol":          symbol,
            "candle_count":    n_candles,
            "market_meta":     market_meta,
            "signals":         individual_results,
            "weights":         weights,
            "combined":        combined,
            "strategy_errors": strategy_errors,
        },
    }


# ============================================================
# UI HELPERS
# ============================================================

SIGNAL_STYLE = {
    "BUY":   {"emoji": "🟢", "color": "#2ecc71"},
    "SELL":  {"emoji": "🔴", "color": "#e74c3c"},
    "HOLD":  {"emoji": "🟡", "color": "#f39c12"},
    "WATCH": {"emoji": "🔵", "color": "#3498db"},
}

def _signal_label(signal: str) -> str:
    s = SIGNAL_STYLE.get(signal, {"emoji": "⚪"})
    return f"{s['emoji']} {signal}"

def _score_bar_html(score: float) -> str:
    pct = max(0, min(100, int((score + 1.0) / 2.0 * 100)))
    if score >= BUY_THRESHOLD:    color = SIGNAL_STYLE["BUY"]["color"]
    elif score <= SELL_THRESHOLD: color = SIGNAL_STYLE["SELL"]["color"]
    else:                          color = SIGNAL_STYLE["HOLD"]["color"]
    return f"""
    <div style="background:#333;border-radius:6px;height:18px;position:relative;">
      <div style="width:{pct}%;background:{color};height:100%;border-radius:6px;
                  transition:width 0.3s ease;"></div>
      <div style="position:absolute;top:0;left:50%;width:2px;height:100%;
                  background:#888;"></div>
    </div>
    <div style="display:flex;justify-content:space-between;
                font-size:0.75em;color:#888;margin-top:2px;">
      <span>◀ SELL</span><span>HOLD</span><span>BUY ▶</span>
    </div>"""


def _source_badge(name: str) -> str:
    """Return a small badge string indicating built-in vs external source."""
    if name not in _external_names:
        return ""
    source = _strategy_meta.get(name, {}).get("source", "external")
    return " 📂" if source == "external-python" else " 📄"
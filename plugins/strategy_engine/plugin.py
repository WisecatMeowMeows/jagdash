# strategy_engine/plugin.py
# JagDash Strategy Engine Plugin v1.4
#
# Provides: market.strategy.signal
# Requires: market.price, market.settings
#
# v1.4 changes:
#   - Conforms to JagDash plugin contract v2: register_routes(), ui_defaults
#   - Passes source through to market.price so strategies use the same
#     data source as market_data plugin (yahoo/hyperliquid/coinmarketcap)
#   - Syncs source from market.settings if not supplied in payload
#   - Removed render_ui() (was Streamlit, already deleted)

import importlib.util
import pandas as pd
import numpy as np

from pathlib import Path


PLUGIN_NAME    = "Strategy Engine"
STRATEGIES_DIR = Path(__file__).parent / "strategies"


# ============================================================
# SIGNAL VOCABULARY
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
# TRADE RECOMMENDATION TUNING
# ============================================================
# Drives the Entry / Target / Stop / Leverage columns in the strategy
# table. All four numbers come from ONE measurement — ATR(14), the
# average bar-to-bar price movement — so they're consistent with each
# other and with the built-in "ATR Trend Filter" strategy.
#
# These are heuristics, not financial advice. Tune freely:
#   RISK_PER_TRADE_PCT  — first knob to turn. Lower = more conservative
#                         leverage suggestions across the board.
#   TARGET_ATR_MULT /
#   STOP_ATR_MULT       — together set the reward:risk ratio
#                         (default 2.0 / 1.0 = 2:1).
#   MIN/MAX_LEVERAGE    — hard floor/ceiling regardless of volatility.
ATR_PERIOD         = 14
TARGET_ATR_MULT    = 2.0
STOP_ATR_MULT      = 1.0
RISK_PER_TRADE_PCT = 10.0
MIN_LEVERAGE       = 1.0
MAX_LEVERAGE       = 10.0


# ============================================================
# MANIFEST
# ============================================================

def manifest() -> dict:
    return {
        "name":     "strategy_engine",
        "version":  "1.4",
        "provides": ["market.strategy.signal"],
        "requires": ["market.price", "market.settings"],
        "ui_defaults": {
            "symbol":   "BTC-USD",
            "interval": "5m",
            "period":   "1mo",
            "source":   "yahoo",
        }
    }


# ============================================================
# GET UI CONTEXT
# ============================================================

def _build_strategy_list() -> list[dict]:
    """Full registry info for every currently-loaded strategy.

    Used both for the initial table render and to rebuild the table
    after /run or /reload, so the row set always matches STRATEGIES.
    """
    strategy_list = []
    for name in STRATEGIES:
        meta = _strategy_meta.get(name, {})
        strategy_list.append({
            "name":        name,
            "type":        meta.get("type", ""),
            "description": meta.get("description", ""),
            "source":      meta.get("source", "built-in"),
            "min_candles": meta.get("min_candles", 0),
            "file":        meta.get("file", ""),
        })
    return strategy_list


def get_ui_context(context):
    """Return data needed by partials/strategy_engine.html.

    Settings (symbol, interval, period, source) are read from market.settings
    and displayed read-only. The user adjusts them in market_data plugin.

    The strategy table is permanent (always rendered), so this also
    supplies the "nothing has run yet" defaults for every column —
    these are the same keys that /run and /reload fill in with real
    results via partials/strategy_table_rows.html and
    partials/strategy_summary.html.
    """
    strategy_list = _build_strategy_list()

    # Fetch current market settings for display (read-only in this plugin)
    market_settings = {
        "symbol":   "BTC-USD",
        "interval": "—",
        "period":   "—",
        "source":   "yahoo",
    }
    settings_error = None
    try:
        result = context.request("market.settings", {})
        if result.get("status") == "success":
            market_settings.update(result["data"])
        else:
            settings_error = result.get("message", "market.settings unavailable")
    except Exception as e:
        settings_error = str(e)

    return {
        "strategies":          strategy_list,
        "errors":              _discovery_errors,
        "market_settings":     market_settings,
        "settings_error":      settings_error,
        # --- permanent table defaults (nothing run yet) ---
        "selected_strategies": list(STRATEGIES.keys()),
        "weights":             {name: DEFAULT_WEIGHT for name in STRATEGIES},
        "signals":             {},
        "signal_scores":       SIGNAL_SCORES,
        "trade_recs":          {},
        "strategy_errors":     {},
        "combined":            None,
        "market_meta":         {},
        "buy_threshold":       BUY_THRESHOLD,
        "sell_threshold":      SELL_THRESHOLD,
        "error":               None,
    }


# ============================================================
# INDICATORS
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


def calculate_atr(series: pd.Series, period: int = ATR_PERIOD) -> pd.Series:
    """
    Close-to-close ATR approximation — no high/low/open needed.
    Same approach as strategies/atr_trend_filter.py, so the volatility
    figure here matches what that strategy is reacting to.
    """
    return series.diff().abs().rolling(period).mean()


# ============================================================
# TRADE RECOMMENDATIONS (Entry / Target / Stop / Leverage)
# ============================================================

def compute_trade_recommendations(df: pd.DataFrame) -> dict:
    """
    One ATR-based volatility measurement -> entry/target/stop for a BUY
    and for a SELL, plus a single leverage suggestion for both.

    Signal-processing framing: ATR is the "noise floor" of the price —
    how much it typically wiggles per bar. Leverage here is just
    (risk budget) / (noise floor): if price moves ~1% per bar and
    you're willing to risk 10% of margin on a stop-out, 10x leverage
    means one "normal" bar eats your whole risk budget. Bigger noise
    floor -> automatically lower leverage, no separate volatility
    check needed.

    Returns {} if there isn't enough history for ATR (e.g. CMC
    free-tier single-candle data) — callers should treat that as
    "no recommendation available", not an error.
    """
    close   = df["close"]
    atr     = calculate_atr(close)

    price   = close.iloc[-1]
    atr_now = atr.iloc[-1]

    if pd.isna(price) or pd.isna(atr_now) or price <= 0 or atr_now <= 0:
        return {}

    atr_pct  = atr_now / price
    leverage = (RISK_PER_TRADE_PCT / 100.0) / atr_pct
    leverage = max(MIN_LEVERAGE, min(MAX_LEVERAGE, leverage))

    return {
        "price":    price,
        "atr":      atr_now,
        "atr_pct":  atr_pct,
        "leverage": leverage,
        "BUY": {
            "entry":  price,
            "target": price + TARGET_ATR_MULT * atr_now,
            "stop":   price - STOP_ATR_MULT  * atr_now,
        },
        "SELL": {
            "entry":  price,
            "target": price - TARGET_ATR_MULT * atr_now,
            "stop":   price + STOP_ATR_MULT  * atr_now,
        },
    }


# ============================================================
# BUILT-IN STRATEGY FUNCTIONS
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
            "volatility is contracting and a breakout is likely building. "
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
# ============================================================

def _build_indicator_value(df: pd.DataFrame, itype: str, params: dict) -> float:
    close = df["close"]
    if itype == "close":
        return float(close.iloc[-1])
    elif itype == "sma":
        return float(close.rolling(int(params.get("period", 20))).mean().iloc[-1])
    elif itype == "ema":
        return float(close.ewm(span=int(params.get("period", 20)),
                                adjust=False).mean().iloc[-1])
    elif itype == "rsi":
        return float(calculate_rsi(close, int(params.get("period", 14))).iloc[-1])
    elif itype == "macd":
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        return float((close.ewm(span=fast, adjust=False).mean()
                      - close.ewm(span=slow, adjust=False).mean()).iloc[-1])
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
        return float(close.rolling(int(params.get("period", 20))).mean().iloc[-1])
    elif itype == "rolling_high":
        return float(close.rolling(int(params.get("period", 20))).max().iloc[-1])
    elif itype == "rolling_low":
        return float(close.rolling(int(params.get("period", 20))).min().iloc[-1])
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
    if not isinstance(cond, list) or len(cond) != 3:
        return False
    left_name, op_str, right = cond
    left_val  = values.get(str(left_name), float("nan"))
    right_val = (values.get(str(right), float("nan"))
                 if isinstance(right, str) else float(right))
    if pd.isna(left_val) or pd.isna(right_val):
        return False
    op_fn = _CONDITION_OPS.get(str(op_str))
    return bool(op_fn(left_val, right_val)) if op_fn else False


def _eval_when(when, values: dict[str, float]) -> bool:
    if isinstance(when, list):
        return _eval_condition(when, values)
    if isinstance(when, dict):
        if "all" in when:
            return all(_eval_condition(c, values) for c in when["all"])
        if "any" in when:
            return any(_eval_condition(c, values) for c in when["any"])
    return False


def _make_declarative_signal_fn(config: dict) -> callable:
    indicators_cfg = config.get("indicators", {})
    rules          = config.get("rules", [])

    def signal(df: pd.DataFrame) -> str:
        try:
            values: dict[str, float] = {}
            for var_name, cfg in indicators_cfg.items():
                if isinstance(cfg, dict):
                    itype  = cfg.get("type", var_name)
                    params = cfg
                else:
                    itype  = str(cfg)
                    params = {}
                values[var_name] = _build_indicator_value(df, itype, params)

            for rule in rules:
                if rule.get("default"):
                    return str(rule.get("signal", "HOLD")).upper()
                when = rule.get("when")
                if when is not None and _eval_when(when, values):
                    sig = str(rule.get("signal", "HOLD")).upper()
                    return sig if sig in SIGNAL_SCORES else "HOLD"
        except Exception:
            pass
        return "HOLD"

    return signal


def _load_declarative_file(path: Path) -> tuple[dict | None, str | None]:
    try:
        import yaml
    except ImportError:
        return None, "PyYAML not installed — run: python -m pip install pyyaml"
    try:
        text   = path.read_text(encoding="utf-8")
        config = yaml.safe_load(text)
    except Exception as e:
        return None, f"Parse error: {e}"
    if not isinstance(config, dict):
        return None, "Top-level structure must be a YAML mapping (key: value)"
    if "rules" not in config:
        return None, "Missing required 'rules' list"
    return config, None


# ============================================================
# EXTERNAL STRATEGY DISCOVERY
# ============================================================

def _discover_external_strategies(
    directory: Path,
) -> tuple[dict[str, callable], dict[str, dict], dict[str, str]]:
    discovered: dict[str, callable] = {}
    meta:       dict[str, dict]     = {}
    errors:     dict[str, str]      = {}

    if not directory.is_dir():
        return discovered, meta, errors

    candidates = sorted(
        p for p in directory.iterdir()
        if p.suffix in {".py", ".yaml", ".yml", ".json"}
        and not p.name.startswith("_")
    )

    for path in candidates:
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
                if hasattr(module, "manifest") and callable(module.manifest):
                    try:
                        m     = module.manifest()
                        name  = m.get("name") or path.stem.replace("_", " ").title()
                        desc  = m.get("description", "")
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
                    m     = {}
                if name in BUILTIN_STRATEGIES:
                    errors[path.name] = f"Note: '{name}' overrides a built-in strategy"
                discovered[name] = module.signal
                meta[name] = {
                    "description": desc,
                    "type":        mtype,
                    "source":      "external-python",
                    "file":        path.name,
                    "min_candles": int(m.get("min_candles", 0)),
                }
            except Exception as e:
                errors[path.name] = f"Load error: {e}"

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
# ACTIVE STRATEGY TABLE
# ============================================================

STRATEGIES:        dict[str, callable] = dict(BUILTIN_STRATEGIES)
_strategy_meta:    dict[str, dict]     = dict(BUILTIN_META)
_discovery_errors: dict[str, str]      = {}
_external_names:   set[str]            = set()


def _reload_strategies() -> None:
    global STRATEGIES, _strategy_meta, _discovery_errors, _external_names
    external, ext_meta, errors = _discover_external_strategies(STRATEGIES_DIR)
    _discovery_errors = errors
    _external_names   = set(external.keys())
    STRATEGIES        = {**BUILTIN_STRATEGIES, **external}
    _strategy_meta    = {**BUILTIN_META, **ext_meta}


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
        if w <= 0.0:
            continue
        weighted_score += w * SIGNAL_SCORES.get(sig, 0.0)
        total_weight   += w
    if total_weight == 0.0:
        return {"signal": "HOLD", "score": 0.0, "confidence": 0.0}
    normalized = weighted_score / total_weight
    if normalized >= BUY_THRESHOLD:    combined = "BUY"
    elif normalized <= SELL_THRESHOLD: combined = "SELL"
    else:                               combined = "HOLD"
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
    if df.empty:
        return None, "Market dataframe is empty"
    if "close" not in df.columns:
        return None, "Missing required 'close' column"
    if len(df) < 3:
        return None, f"Market data too short: {len(df)} candle(s); need at least 3"
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    if df["close"].isna().all():
        return None, "All 'close' values are non-numeric"
    return df, None


# ============================================================
# MARKET METADATA EXTRACTOR
# ============================================================

def _infer_period_string(candle_count: int, interval: str) -> tuple[str, bool]:
    INTRADAY_MINUTES: dict[str, int] = {
        "1m": 1, "2m": 2, "5m": 5, "15m": 15,
        "30m": 30, "60m": 60, "90m": 90, "1h": 60,
    }
    assumed = (interval not in INTRADAY_MINUTES
               and interval not in {"1d", "1wk", "1mo"})
    if interval == "1d" or assumed:
        days = candle_count
        if days < 14:    return f"~{days} days", assumed
        elif days < 60:  return f"~{days / 7:.1f} wk", assumed
        elif days < 365: return f"~{days / 30.44:.1f} mo", assumed
        else:            return f"~{days / 365.25:.2f} yr", assumed
    if interval == "1wk":
        weeks = candle_count
        if weeks < 8:   return f"~{weeks} wk", False
        elif weeks < 52: return f"~{weeks / 4.33:.1f} mo", False
        else:            return f"~{weeks / 52:.2f} yr", False
    if interval == "1mo":
        months = candle_count
        if months < 12: return f"~{months} mo", False
        else:           return f"~{months / 12:.1f} yr", False
    total_minutes = candle_count * INTRADAY_MINUTES[interval]
    if total_minutes < 120:          return f"~{int(total_minutes)} min", False
    elif total_minutes <= 60 * 48:   return f"~{total_minutes / 60:.1f} hr", False
    elif total_minutes < 390 * 15:   return f"~{total_minutes / 390:.0f} trading days", False
    elif total_minutes < 390 * 63:   return f"~{total_minutes / (390 * 5):.1f} wk", False
    elif total_minutes < 390 * 252:  return f"~{total_minutes / (390 * 21):.1f} mo", False
    else:                             return f"~{total_minutes / (390 * 252):.2f} yr", False


def _extract_market_meta(
    market_response: dict,
    df: pd.DataFrame,
    symbol: str,
) -> dict:
    meta:     dict = {}
    provided: dict = market_response.get("meta") or {}
    meta["symbol"]       = symbol
    meta["candle_count"] = provided.get("candles", len(df))
    meta["interval"]     = provided.get("interval", "1d")
    meta["columns"]      = provided.get("columns") or sorted(df.columns.tolist())
    close = df["close"].dropna()
    if not close.empty:
        meta["price_last"] = round(float(close.iloc[-1]), 6)
        meta["price_min"]  = round(float(close.min()),    6)
        meta["price_max"]  = round(float(close.max()),    6)
    for key in ("source", "source_label", "asset_class", "currency"):
        if key in provided:
            meta[key] = provided[key]
    start_date = provided.get("start")
    end_date   = provided.get("end")
    if start_date and end_date:
        meta["period_str"]       = f"{start_date}  →  {end_date}"
        meta["period_estimated"] = False
    elif provided.get("period"):
        meta["period_str"]       = provided["period"]
        meta["period_estimated"] = False
    else:
        span, unrecognized       = _infer_period_string(meta["candle_count"],
                                                         meta["interval"])
        meta["period_str"]       = span
        meta["period_estimated"] = True
    return meta


# ============================================================
# HANDLE REQUEST
# ============================================================

def handle_request(request: dict, context) -> dict:
    capability = request.get("capability")
    payload    = request.get("payload", {})

    if capability != "market.strategy.signal":
        return {"status": "error",
                "message": f"Unsupported capability: {capability}"}

    symbol   = payload.get("symbol",    "BTC-USD")
    interval = payload.get("interval",  "5m")
    period   = payload.get("period",    "1mo")
    selected = payload.get("strategies", list(STRATEGIES.keys()))
    weights  = payload.get("weights",   {n: DEFAULT_WEIGHT for n in selected})

    # ── Source resolution ────────────────────────────────────────────────
    # Priority:
    #   1. Explicitly passed in payload (e.g. from strategy_engine UI)
    #   2. Current source from market.settings (keeps in sync with market_data)
    #   3. Default "yahoo"
    #
    # This means strategy_engine always uses the same data source as
    # market_data without requiring the user to configure it twice.
    source = payload.get("source")
    if not source:
        try:
            settings = context.request("market.settings", {})
            if settings.get("status") == "success":
                source = settings["data"].get("source", "yahoo")
        except Exception:
            pass
    if not source:
        source = "yahoo"

    unknown = [s for s in selected if s not in STRATEGIES]
    if unknown:
        return {"status": "error",
                "message": f"Unknown strategy name(s): {unknown}"}
    if not selected:
        return {"status": "error", "message": "No strategies selected"}

    try:
        market_response = context.request(
            "market.price",
            {
                "symbol":   symbol,
                "interval": interval,
                "period":   period,
                "source":   source,   # ← pass source through to market_data
            },
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
        min_c = _strategy_meta.get(name, {}).get("min_candles", 0)
        if min_c and n_candles < min_c:
            individual_results[name] = "HOLD"
            strategy_errors[name]    = (
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
    trade_recs  = compute_trade_recommendations(df)

    return {
        "status": "success",
        "data": {
            "symbol":          symbol,
            "source":          source,
            "candle_count":    n_candles,
            "market_meta":     market_meta,
            "signals":         individual_results,
            "weights":         weights,
            "combined":        combined,
            "strategy_errors": strategy_errors,
            "trade_recs":      trade_recs,
        },
    }


# ============================================================
# UI HELPERS (used by templates)
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


def _source_badge(name: str) -> str:
    if name not in _external_names:
        return ""
    source = _strategy_meta.get(name, {}).get("source", "external")
    return " 📂" if source == "external-python" else " 📄"


# ============================================================
# ROUTE REGISTRATION
# ============================================================

def register_routes(app, templates, get_host):
    """
    Register strategy_engine HTTP routes onto the FastAPI app.
    Called once at startup — no changes to main.py needed.
    """
    from fastapi import Form, Request
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext
    from typing import List, Optional

    def _render(template_name: str, **ctx) -> str:
        return templates.env.get_template(template_name).render(**ctx)

    def _default_table_state() -> dict:
        """'Nothing has run yet' / 'strategies just reloaded' table state."""
        return {
            "strategies":          _build_strategy_list(),
            "selected_strategies": list(STRATEGIES.keys()),
            "weights":             {name: DEFAULT_WEIGHT for name in STRATEGIES},
            "signals":             {},
            "signal_scores":       SIGNAL_SCORES,
            "trade_recs":          {},
            "strategy_errors":     {},
        }

    def _default_summary_state(error: str | None = None) -> dict:
        return {
            "error":           error,
            "combined":        None,
            "market_meta":     {},
            "strategy_errors": {},
            "buy_threshold":   BUY_THRESHOLD,
            "sell_threshold":  SELL_THRESHOLD,
        }

    @app.post("/plugin/strategy_engine/reload", response_class=HTMLResponse)
    async def strategy_engine_reload(request: Request):
        """
        Reload external strategy files without restarting the server.

        Also refreshes the permanent table: the strategy set may have
        changed (a file was added/removed/edited), so any previously
        displayed signals/weights/results no longer correspond to a
        known-good run and are reset to placeholders.
        """
        _reload_strategies()
        count = len(STRATEGIES)
        ext   = len(_external_names)
        errs  = len(_discovery_errors)
        msg   = f"Reloaded. {count} strategies ({ext} external)"
        if errs:
            msg += f", {errs} issue(s) — check strategy list."

        rows_html      = _render("partials/strategy_table_rows.html", **_default_table_state())
        summary_html   = _render("partials/strategy_summary.html", **_default_summary_state())
        discovery_html = _render("partials/strategy_discovery_errors.html", errors=_discovery_errors)

        return HTMLResponse(
            f'<div class="success-msg">{msg}</div>'
            f'<div id="strategy-table-container" class="table-wrapper" hx-swap-oob="true">{rows_html}</div>'
            f'<div id="strategy-summary" hx-swap-oob="true">{summary_html}</div>'
            f'<div id="strategy-discovery-errors" hx-swap-oob="true">{discovery_html}</div>'
        )

    @app.post("/plugin/strategy_engine/run", response_class=HTMLResponse)
    async def strategy_engine_run(
        request:             Request,
        selected_strategies: Optional[List[str]] = Form(None),
    ):
        """
        Run strategy analysis using current market_data settings.
        Symbol, interval, period, and source are read from market.settings
        rather than from form fields — the user sets them in market_data.

        The strategy table is permanent: every call re-renders the full
        tbody (every known strategy, checkboxes/weights preserved from
        the submitted form) plus the combined-signal summary, both
        delivered as hx-swap-oob fragments. The form itself uses
        hx-swap="none" — nothing is swapped into the form's own target,
        only the two OOB elements.
        """
        # weight_* inputs exist for every row regardless of checkbox
        # state, so this dict covers selected AND unselected strategies —
        # that's what lets the table preserve weights for rows the user
        # didn't run this time.
        form_data = await request.form()
        weights   = {}
        for key, value in form_data.multi_items():
            if key.startswith("weight_"):
                name = key[len("weight_"):]
                try:
                    weights[name] = float(value)
                except (ValueError, TypeError):
                    weights[name] = DEFAULT_WEIGHT

        selected_strategies = selected_strategies or []
        for name in STRATEGIES:
            weights.setdefault(name, DEFAULT_WEIGHT)

        signals         = {}
        trade_recs      = {}
        strategy_errors = {}
        combined        = None
        market_meta     = {}
        summary_error   = None

        if not selected_strategies:
            summary_error = "No strategies selected."
        else:
            host    = get_host(request)
            context = PluginContext(host)

            # Read current market settings — single source of truth
            try:
                settings_result = context.request("market.settings", {})
                ms = (settings_result["data"]
                      if settings_result.get("status") == "success" else {})
            except Exception:
                ms = {}

            symbol   = ms.get("symbol",   "BTC-USD")
            interval = ms.get("interval", "5m")
            period   = ms.get("period",   "1mo")
            source   = ms.get("source",   "yahoo")

            try:
                result = context.request(
                    "market.strategy.signal",
                    {
                        "symbol":     symbol,
                        "interval":   interval,
                        "period":     period,
                        "source":     source,
                        "strategies": selected_strategies,
                        "weights":    weights,
                    }
                )
            except Exception as e:
                summary_error = str(e)
            else:
                if result["status"] != "success":
                    summary_error = result.get("message", "Unknown error")
                else:
                    data            = result["data"]
                    signals         = data.get("signals", {})
                    trade_recs      = data.get("trade_recs", {})
                    strategy_errors = data.get("strategy_errors", {})
                    combined        = data.get("combined")
                    market_meta     = data.get("market_meta", {})

        rows_html = _render(
            "partials/strategy_table_rows.html",
            strategies=_build_strategy_list(),
            selected_strategies=selected_strategies,
            weights=weights,
            signals=signals,
            signal_scores=SIGNAL_SCORES,
            trade_recs=trade_recs,
            strategy_errors=strategy_errors,
        )
        summary_html = _render(
            "partials/strategy_summary.html",
            error=summary_error,
            combined=combined,
            market_meta=market_meta,
            strategy_errors=strategy_errors,
            buy_threshold=BUY_THRESHOLD,
            sell_threshold=SELL_THRESHOLD,
        )

        return HTMLResponse(
            f'<div id="strategy-table-container" class="table-wrapper" hx-swap-oob="true">{rows_html}</div>'
            f'<div id="strategy-summary" hx-swap-oob="true">{summary_html}</div>'
        )

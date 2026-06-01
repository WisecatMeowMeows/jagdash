# ARCHITECTURE.md
## JagDash System Architecture

Version: 1.1

---

## What JagDash Is

JagDash is a **plugin-based dashboard framework** built on Streamlit.
It provides the infrastructure — routing, rendering, event broadcasting — so that plugin authors can focus purely on domain logic.

The core system is intentionally thin. Almost all functionality lives in plugins.

---

## Hub-and-Spoke Architecture

```
                        ┌─────────────┐
                        │  PluginHost │
                        │   (Hub)     │
                        └──────┬──────┘
               ┌───────────────┼───────────────┐
               │               │               │
        ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐
        │ market_data │ │strategy_eng │ │  my_plugin  │
        │  (plugin)   │ │  (plugin)   │ │  (plugin)   │
        └─────────────┘ └─────────────┘ └─────────────┘
```

Plugins never talk directly to each other. All communication goes through PluginHost.

This means:
- Plugins are interchangeable — swap `market_data` for a different data source and `strategy_engine` never knows
- Plugins are independently testable
- A broken plugin cannot crash another plugin (only its own request chain)

---

## Two Communication Channels

### 1. Request / Response (synchronous)

One plugin asks PluginHost for a capability. PluginHost finds the plugin that provides it, calls `handle_request()`, and returns the result.

```
strategy_engine ──request("market.price")──► PluginHost ──► market_data
strategy_engine ◄──────────response────────── PluginHost ◄── market_data
```

Use this when you need data before you can continue.

### 2. Publish / Subscribe (fire and forget)

A plugin broadcasts an event. Any component that has subscribed to that event receives it.

```
market_data ──publish("market.tick", {...})──► PluginHost ──► [all subscribers]
```

Use this to notify the rest of the system that something happened, without caring who's listening.

---

## Plugin Lifecycle

When JagDash starts:

1. It scans the plugins directory for all `plugin.py` files
2. It calls `manifest()` on each to build the capability registry
3. It wires up the routing table: capability string → plugin
4. It calls `render_ui(context)` for each plugin to build the dashboard

At runtime:
- UI interactions trigger `context.request()` calls
- `handle_request()` is called on the appropriate plugin
- Plugins may chain requests to other plugins
- Results flow back up the chain

---

## Capability Registry

The registry is built at startup from all loaded `manifest()` calls.

| Capability | Provided By |
|---|---|
| `market.price` | `market_data` |
| `market.strategy.signal` | `strategy_engine` |

When you add a new plugin, add its capabilities to this table in your local notes.
PluginHost builds this automatically — this table is for human reference only.

---

## Known Plugins

### `market_data`
- **Provides:** `market.price`
- **Requires:** nothing (self-contained)
- **Output format:** list of `{"close": float}` dicts, daily candles, ~126 rows (6 months)
- **Data source:** Yahoo Finance via `yfinance`
- **Publishes:** `market.tick` with latest close price

### `strategy_engine`
- **Provides:** `market.strategy.signal`
- **Requires:** `market.price`
- **Output format:** `{"symbol": str, "strategy": str, "signal": str}`
- **Signal values:** `BUY`, `SELL`, `HOLD`, `WATCH`
- **Minimum data requirement:** 50 candles
- **Available strategies:** SMA Crossover, RSI Mean Reversion, MACD Trend, Breakout Momentum, Volatility Compression
- **Publishes:** `strategy.signal.generated`

---

## Environment Setup

```bash
# Create virtual environment
python -m venv jagdash_env

# Activate (run this every session)
source jagdash_env/bin/activate        # macOS / Linux
jagdash_env\Scripts\activate           # Windows

# Install base dependencies
python -m pip install streamlit pandas numpy yfinance

# Launch JagDash
streamlit run app.py
```

**Critical:** Always use `python -m pip install` (not bare `pip install`) to guarantee packages install into the active venv. Always launch `streamlit` from within the activated venv.

---

## Adding a New Plugin

1. Create a new file: `plugins/my_plugin.py`
2. Implement `manifest()`, `handle_request()`, and optionally `render_ui()`
3. Add any new dependencies to `requirements.txt`
4. Restart JagDash — it will auto-discover the new plugin
5. Update the Known Plugins table above

---

## Design Principles

**Plugins are domain-specific.**
Each plugin should do one thing. A plugin that fetches prices should not also compute signals.

**Payloads may evolve, structure must not.**
The request/response envelope (`status`, `data`, `message`) is fixed. What's inside `data` and `payload` can grow over time. Consumers must use `.get()` and handle missing fields gracefully.

**Fail loudly within, fail gracefully outward.**
Inside your plugin, use assertions and raise errors freely during development. At the boundary — `handle_request()` — catch everything and return a proper error response. Never let an exception escape `handle_request()`.

**No shared state between plugins.**
Plugins must not write to global variables that other plugins read. Use events for notification, requests for data.

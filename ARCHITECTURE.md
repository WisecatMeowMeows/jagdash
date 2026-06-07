# ARCHITECTURE.md
## JagDash System Architecture

Version: 2.0 (FastAPI)

---

## What JagDash Is

JagDash is a **plugin-based dashboard framework** built on FastAPI + HTMX.
It provides the infrastructure — routing, rendering, event broadcasting,
authentication, theming — so that plugin authors can focus purely on domain logic.

The core system is intentionally thin. Almost all functionality lives in plugins.

JagDash is the platform. NiteTrader (crypto trading tool) is one configuration
that runs on JagDash. Any domain-specific dashboard can be built the same way.

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
- Plugins are interchangeable — swap `market_data` for a different data source
  and `strategy_engine` never knows
- Plugins are independently testable
- A broken plugin cannot crash another plugin (only its own request chain)

---

## Web Layer

```
Browser
  │
  │  HTTP (GET page, POST form via HTMX)
  ▼
FastAPI (main.py)
  │  renders HTML via Jinja2 templates
  │  calls PluginHost for data
  │
  ▼
PluginHost → Plugin.handle_request() → data
```

**FastAPI** serves pages and handles form submissions.
**HTMX** updates page fragments without full reloads — button clicks send POST
requests and the response HTML replaces only the relevant section of the page.
**Jinja2** renders HTML templates server-side before sending to the browser.
**CSS custom properties** in `jagdash.css` drive the theme system.

---

## Two Communication Channels

### 1. Request / Response (synchronous)

One plugin asks PluginHost for a capability. PluginHost finds the plugin
that provides it, calls `handle_request()`, and returns the result.

```
strategy_engine ──request("market.price")──► PluginHost ──► market_data
strategy_engine ◄──────────response────────── PluginHost ◄── market_data
```

Use this when you need data before you can continue.

### 2. Publish / Subscribe (fire and forget)

A plugin broadcasts an event. Any component subscribed to that event receives it.

```
market_data ──publish("market.tick", {...})──► PluginHost ──► [all subscribers]
```

Use this to notify the rest of the system that something happened,
without caring who's listening.

---

## Plugin Lifecycle

When JagDash starts (uvicorn main:app):

1. `plugin_loader.py` scans the `plugins/` directory for `plugin.py` files
2. Each plugin's `manifest()` is called to build the capability registry
3. The routing table is built: capability string → plugin
4. Each plugin's `register_routes()` is called (if defined) to register
   its HTTP routes directly onto the FastAPI app
5. The server starts listening for requests

At runtime:
- Browser navigates to a plugin → `GET /plugin/{name}` → `get_ui_context()` →
  Jinja2 renders the plugin's HTML partial
- User submits a form → `POST /plugin/{name}/action` → plugin's registered
  route handler → `context.request()` → `handle_request()` → result →
  Jinja2 renders the results partial → HTMX swaps it into the page

---

## File Structure

```
jagdash/
├── main.py                    # FastAPI app, startup, auth, config routes
├── host.py                    # PluginHost — the hub
├── plugin_loader.py           # scans plugins/ directory at startup
├── plugin_context.py          # PluginContext — wraps PluginHost for plugins
├── plugin_template.py         # starter template for new plugins
├── example_plugin.py          # minimal working example
├── theme_engine.py            # reads theme from profile, generates CSS
├── auth.py                    # bcrypt password hashing, session auth helpers
├── config_manager.py          # reads/writes jagdash_profiles.json
├── event_bus.py               # pub/sub event routing
├── request_schema.py          # validates request dicts
│
├── plugins/
│   ├── market_data/
│   │   └── plugin.py          # provides market.price, market.settings
│   ├── strategy_engine/
│   │   ├── plugin.py          # provides market.strategy.signal
│   │   └── strategies/        # YAML and Python strategy files (auto-discovered)
│   ├── news_scanner/
│   │   └── plugin.py          # provides news.search
│   ├── news_signal/
│   │   └── plugin.py          # provides news.signal
│   ├── news_feed/
│   │   └── plugin.py          # provides news.headlines
│   ├── overview/
│   │   └── plugin.py          # provides overview.summary
│   ├── config_plugin/
│   │   └── plugin.py          # no capability; UI for profile/theme/key management
│   └── alert_engine/
│       └── plugin.py          # subscribes to market.tick
│
├── templates/
│   ├── base.html              # page shell: sidebar, main content area, CSS/JS
│   ├── login.html             # authentication page
│   └── partials/              # plugin UI fragments (one per plugin)
│       ├── market_data.html
│       ├── market_data_results.html
│       ├── strategy_engine.html
│       ├── strategy_engine_results.html
│       ├── news_scanner.html
│       ├── news_scanner_results.html
│       ├── news_signal.html
│       ├── news_signal_results.html
│       ├── overview.html
│       ├── overview_results.html
│       ├── config_plugin.html
│       └── theme_form.html
│
├── static/
│   ├── jagdash.css            # all styling, CSS custom properties for theming
│   └── htmx.min.js            # HTMX library (served locally, no CDN)
│
└── images/                    # user-supplied images (logo, background)
```

---

## Capability Registry

Built automatically at startup from all loaded `manifest()` calls.

| Capability | Plugin | Output |
|---|---|---|
| `market.price` | `market_data` | `list[{open,high,low,close,volume,date}]` |
| `market.settings` | `market_data` | `{symbol, interval, period}` |
| `market.strategy.signal` | `strategy_engine` | `{combined, signals, weights, market_meta}` |
| `news.search` | `news_scanner` | `list[article]` (NewsAPI format) |
| `news.signal` | `news_signal` | `{signal, bullish_total, bearish_total, articles}` |
| `news.headlines` | `news_feed` | `{headlines: [str]}` |
| `overview.summary` | `overview` | `{results: {market_price, strategy, news_signal, news_headlines}}` |

---

## Known Plugins

### `market_data`
- **Provides:** `market.price`, `market.settings`
- **Requires:** nothing
- **Data source:** Yahoo Finance via yfinance
- **Publishes:** `market.tick` with latest close price

### `strategy_engine`
- **Provides:** `market.strategy.signal`
- **Requires:** `market.price`
- **Strategies:** built-in Python + external YAML/Python files in `strategies/`
- **External strategies:** drop a `.py` or `.yaml` file in `strategies/`, reload
- **Publishes:** `strategy.signal.generated`

### `news_scanner`
- **Provides:** `news.search`
- **Requires:** nothing (calls NewsAPI directly)
- **API key:** `NEWSAPI_KEY` in `.env` or config plugin UI

### `news_signal`
- **Provides:** `news.signal`
- **Requires:** `news.search`
- **Method:** keyword scoring (bullish/bearish word lists)
- **Publishes:** `news.signal_generated`

### `news_feed`
- **Provides:** `news.headlines`
- **Requires:** nothing
- **Note:** currently a stub returning placeholder headlines

### `overview`
- **Provides:** `overview.summary`
- **Requires:** `market.price`, `market.strategy.signal`, `news.signal`, `news.headlines`
- **Purpose:** aggregates outputs from all other plugins into one summary view

### `config_plugin`
- **Provides:** nothing (no capabilities)
- **Requires:** nothing
- **Purpose:** UI for profile management, theme editor, API key storage

### `alert_engine`
- **Provides:** nothing
- **Subscribes to:** `market.tick`
- **Purpose:** fires alerts when price thresholds are crossed

---

## Infrastructure Components

### Theme Engine (`theme_engine.py`)
Reads a theme dict from the active profile and generates CSS custom property
overrides injected into every page. Users adjust theme via the config plugin
UI — no CSS editing required. Five built-in presets; fully customizable.

### Authentication (`auth.py`)
Single-password bcrypt authentication via session cookie. Password hash stored
in `.env` as `JAGDASH_PASSWORD_HASH`. Generate with `python auth.py`.
If no password is set, auth is bypassed (local development mode).

### Profile System (`config_manager.py`)
Profiles stored in `jagdash_profiles.json`. Each profile holds dashboard name,
logo path, theme settings, plugin enable/disable state, and API keys.
Multiple profiles supported; switch via config plugin UI.

---

## Adding a New Plugin

1. Create `plugins/your_plugin/plugin.py`
2. Implement `manifest()` with `ui_defaults`, `handle_request()`,
   optionally `get_ui_context()` and `register_routes()`
3. Create `templates/partials/your_plugin.html`
4. Create `templates/partials/your_plugin_results.html`
5. Add any new dependencies to `requirements.txt`
6. Restart JagDash — plugin appears in sidebar automatically

**No changes to `main.py` needed.** Routes are registered via `register_routes()`.

See `QUICKSTART.md` for a step-by-step walkthrough.
See `PLUGIN_API.md` for the full API reference.

---

## Design Principles

**Plugins are domain-specific.**
Each plugin does one thing. A plugin that fetches prices should not also compute signals.

**Payloads may evolve, structure must not.**
The request/response envelope (`status`, `data`, `message`) is fixed.
What's inside `data` and `payload` can grow. Consumers use `.get()`.

**Fail loudly within, fail gracefully outward.**
Inside your plugin, raise freely during development. At the boundary —
`handle_request()` — catch everything and return a proper error response.

**No shared state between plugins.**
Plugins must not write to global variables that other plugins read.
Use events for notification, requests for data.

**No changes to main.py for new plugins.**
main.py is infrastructure. Plugin-specific routes belong in the plugin.

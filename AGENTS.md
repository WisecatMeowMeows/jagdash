# AGENTS.md — JagDash AI Context Document
# Paste this at the start of any AI session working on this codebase.
# Last updated: 2026-06

---

## STACK

```
Backend:  Python, FastAPI, uvicorn
Templating: Jinja2 (server-side rendering)
Frontend: HTMX (no JS framework), plain CSS (CSS custom properties)
Auth:     bcrypt + Starlette SessionMiddleware
Run:      uvicorn main:app --reload --port 8000
Repo:     https://github.com/WisecatMeowMeows/jagdash
```

No Streamlit. No React. No npm. No CDN dependencies (HTMX served from static/).

---

## ENTRY POINTS

```
main.py              FastAPI app. Infrastructure only: auth, config, theme routes.
                     Plugin routes are NOT defined here — see register_routes().
host.py              PluginHost — the hub. All plugin communication routes through it.
plugin_loader.py     Scans plugins/ at startup, loads plugin.py files.
theme_engine.py      Reads profile["theme"] dict, generates CSS :root overrides.
auth.py              bcrypt helpers + CLI: python auth.py to generate password hash.
config_manager.py    Reads/writes jagdash_profiles.json.
```

---

## PLUGIN CONTRACT

Every plugin is `plugins/{name}/plugin.py`. Four functions:

### manifest() -> dict  [REQUIRED]
```python
{
    "name":        str,          # unique, snake_case, matches directory name
    "version":     str,          # "1.0"
    "provides":    [str],        # capability strings this plugin handles
    "requires":    [str],        # capabilities called via context.request()
    "ui_defaults": {str: any},   # default form field values; keys match HTML name= attrs
}
```

### handle_request(request, context) -> dict  [REQUIRED]
```python
# Input
request = {"capability": str, "payload": dict}

# Output — always one of:
{"status": "success", "data": <json-serializable>}
{"status": "error",   "message": str}

# Rules:
# - Never raise. Catch all exceptions, return error dict.
# - payload.get("key", default) always — never assume key exists.
# - Wrap every context.request() in try/except.
# - Check response["status"] before using response["data"].
```

### get_ui_context(context) -> dict  [OPTIONAL]
```python
# Returns extra template variables for templates/partials/{name}.html
# The session-restored "ui" dict is merged in automatically — don't return it.
# Called on every GET /plugin/{name} — keep lightweight.
```

### register_routes(app, templates, get_host)  [OPTIONAL]
```python
# Registers this plugin's HTTP routes onto the FastAPI app.
# Called once at startup. NO CHANGES TO main.py NEEDED.

def register_routes(app, templates, get_host):
    from fastapi import Form, Request          # import INSIDE function
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext

    @app.post("/plugin/{name}/action", response_class=HTMLResponse)
    async def action(
        request: Request,                      # MUST be Request, never object
        field:   str = Form("default"),
    ):
        request.session["ui_{name}"] = {"field": field}   # save for restore
        host    = get_host(request)
        context = PluginContext(host)
        try:
            result = context.request("capability.name", {"field": field})
        except Exception as e:
            return HTMLResponse(f'<div class="error-msg">{e}</div>')
        if result["status"] != "success":
            return HTMLResponse(f'<div class="error-msg">{result["message"]}</div>')
        return templates.TemplateResponse(
            request=request,
            name="partials/{name}_results.html",
            context={"data": result["data"], "error": None}
        )
```

**Critical:** `request: Request` not `request: object` — wrong type causes 422 error.
**Critical:** Import fastapi inside register_routes, not at module top level.

---

## CONTEXT API

```python
context.request(capability, payload) -> dict   # call another plugin; raises if not found
context.publish(event, payload)                # fire-and-forget; no return value
context.get_active_profile() -> dict           # current profile dict
context.get_api_key("newsapi") -> str          # reads profile then .env fallback
```

---

## SESSION STATE

```python
# Plugin saves its form state:
request.session["ui_{plugin_name}"] = {"symbol": "BTC-USD", "interval": "5m"}

# main.py restores it via get_plugin_state() which merges:
#   manifest["ui_defaults"]  (lowest priority)
#   session["ui_{name}"]     (highest priority)
# Result passed to template as "ui" variable.
```

---

## TEMPLATES

```
templates/base.html                     Page shell. Has sidebar, #main-content, theme <style>.
templates/login.html                    Auth page. Standalone, no sidebar.
templates/partials/{name}.html          Plugin UI panel (fragment, no <html>/<head>/<body>).
templates/partials/{name}_results.html  Results fragment returned by POST route.
templates/partials/theme_form.html      Reusable theme editor form (included by config_plugin).
```

### Template variables
```
{{ dashboard_name }}     From active profile
{{ plugins }}            List of plugin name strings for sidebar
{{ theme_css_content }}  Raw CSS for <style id="jagdash-theme">
{{ logo_path }}          Normalized absolute URL or empty string
{{ ui.field_name }}      Session-restored form field value (use in value="")
```

### HTMX form pattern
```html
<form hx-post="/plugin/{name}/action"
      hx-target="#results-div"
      hx-swap="innerHTML"
      hx-indicator="#loading-div">
    <input name="field" value="{{ ui.field }}" class="text-input">
    <button type="submit" class="btn btn--primary">Run</button>
</form>
<div id="loading-div" class="htmx-indicator loading-inline">Working…</div>
<div id="results-div" class="results-area">
    <p class="placeholder-msg">Results appear here.</p>
</div>
```

### OOB swap pattern (update elements outside hx-target)
```html
<!-- Server returns this alongside the normal response: -->
<h1 id="dashboard-title" hx-swap-oob="true">New Title</h1>
<style id="jagdash-theme" hx-swap-oob="true">:root { --color-bg: #000; }</style>
```

---

## CSS SYSTEM

All styling in `static/jagdash.css`. Theme via CSS custom properties on `:root`.
`theme_engine.py` generates overrides injected into every page as `<style id="jagdash-theme">`.

Key custom properties:
```css
--color-bg, --color-surface, --color-surface-raised, --color-border
--color-fg, --color-fg-muted, --color-accent
--color-success, --color-error, --color-warning
--font-size-base, --space-xs/sm/md/lg/xl/2xl, --sidebar-width
--border-radius-sm/md/lg
```

CSS classes to use in templates:
```
.plugin-panel, .plugin-header, .plugin-subtitle
.controls-row, .control-group, .control-group--btn
.text-input, .select-input
.btn, .btn--primary, .btn--secondary, .btn--large
.results-area, .placeholder-msg, .results-content
.error-msg, .success-msg, .info-msg
.metric-card, .metric-label, .metric-value
.data-table, .table-wrapper, .td-num, .td-date
.config-section, .config-card, .config-card--wide, .config-row
.signal-pill signal-pill--buy/sell/hold/watch
.signal-hero signal-hero--buy/sell/hold/watch/bullish/bearish/neutral
.htmx-indicator, .loading-inline, .loading-bar
```

---

## KNOWN CAPABILITIES

| Capability | Plugin | data shape |
|---|---|---|
| `market.price` | market_data | `list[{open,high,low,close,volume,date}]` |
| `market.settings` | market_data | `{symbol,interval,period}` |
| `market.strategy.signal` | strategy_engine | `{combined,signals,weights,market_meta,strategy_errors}` |
| `news.search` | news_scanner | `list[article]` NewsAPI format |
| `news.signal` | news_signal | `{signal,bullish_total,bearish_total,articles}` |
| `news.headlines` | news_feed | `{headlines:[str]}` stub |
| `overview.summary` | overview | `{results:{market_price,strategy,news_signal,news_headlines}}` |

Signal vocabulary: `BUY SELL HOLD WATCH` only.

---

## PROFILES & THEME

```python
# jagdash_profiles.json structure
{
    "active_profile": "default",
    "profiles": {
        "default": {
            "dashboard_name": str,
            "logo_path": str,          # relative path, theme_engine normalizes to absolute
            "theme": {                  # dict (new) or str preset name (legacy)
                "preset": str,         # "dark"|"light"|"night_trader"|"compact"|"high_contrast"
                # per-field overrides: color_bg, font_size_base, space_scale, etc.
            },
            "plugins": {name: {"enabled": bool}},
            "api_keys": {"newsapi": str},
            "overview": {symbol, news_query, interval, period}
        }
    }
}

# theme_engine.get_theme(profile) handles legacy string format gracefully
# normalize_asset_path(path) converts any relative path to absolute URL
```

---

## FILE LOCATIONS

```
plugins/{name}/plugin.py              Plugin logic
templates/partials/{name}.html        Plugin UI panel
templates/partials/{name}_results.html Plugin results fragment
static/jagdash.css                    All CSS
static/htmx.min.js                   HTMX (local copy)
images/                              User images (logo, background)
jagdash_profiles.json                Profile/theme/key storage
.env                                 JAGDASH_PASSWORD_HASH, SESSION_SECRET, NEWSAPI_KEY
auth.py                              Run with python auth.py to set password
diagnose.py                          Run to debug startup errors
```

---

## HARD RULES

```
NEVER  import streamlit anywhere
NEVER  add plugin-specific routes to main.py — use register_routes()
NEVER  use request: object in route handlers — always request: Request
NEVER  import fastapi at plugin module top level — import inside register_routes()
NEVER  store secrets in .py or .json files — use .env
NEVER  use HX-Refresh header — causes fragment-only page loads; use hx-swap-oob instead
ALWAYS wrap context.request() in try/except
ALWAYS return {"status":"success"/"error"} from handle_request — never raise
ALWAYS use payload.get("key", default) — never assume payload keys exist
ALWAYS save form state: request.session["ui_{name}"] = {...} in POST handlers
ALWAYS use value="{{ ui.field }}" in form inputs for session restore
ALWAYS normalize image/logo paths through normalize_asset_path() before use in CSS/HTML
```

---

## KNOWN GOTCHAS

```
422 on form POST       → request: object instead of request: Request in route handler
Theme not applying     → profile["theme"] may be legacy string; get_theme() handles it
Image not rendering    → path is relative; use normalize_asset_path() or prefix with /
Plugin missing         → plugin.py not in plugins/{name}/ subdirectory
Jinja2 parse error     → {% %} tags inside HTML comments are executed, not ignored
Session lost           → SessionMiddleware needs itsdangerous installed
Page goes blank        → HX-Refresh navigated to fragment URL; use hx-swap-oob instead
HTMX not working       → check /static/htmx.min.js returns 200 and ~47KB
```

---

## ADDING A PLUGIN (checklist)

```
[ ] plugins/{name}/plugin.py with manifest(), handle_request(), register_routes()
[ ] manifest() has ui_defaults with keys matching HTML form name= attributes
[ ] register_routes() imports Request from fastapi inside the function
[ ] register_routes() saves request.session["ui_{name}"] = {...}
[ ] templates/partials/{name}.html exists
[ ] templates/partials/{name}_results.html exists
[ ] Form inputs use value="{{ ui.field }}" for session restore
[ ] New pip dependencies added to requirements.txt
[ ] Restart uvicorn to pick up new plugin
```

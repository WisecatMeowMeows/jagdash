# PLUGIN_API.md
## JagDash Plugin API Reference

Version: 2.0 (FastAPI)

---

## Overview

JagDash uses a **mediator / hub-and-spoke architecture**.

Plugins do **not** communicate directly with one another.
All requests and events flow through `PluginHost`, which acts as the central router.

The web layer is **FastAPI + HTMX**. Plugins register their own HTTP routes
via `register_routes()` — no changes to `main.py` are needed when adding a plugin.

---

## Plugin File Structure

Each plugin lives in its own subdirectory:

```
plugins/
    your_plugin/
        plugin.py        ← required
```

`plugin.py` must implement:

| Function | Required | Purpose |
|---|---|---|
| `manifest()` | Yes | Declares plugin identity, capabilities, and UI defaults |
| `handle_request(request, context)` | Yes | Handles capability requests from other plugins |
| `get_ui_context(context)` | No | Provides data for the plugin's Jinja2 template |
| `register_routes(app, templates, get_host)` | No | Registers HTTP routes for the plugin's UI actions |

The UI lives in two template files:

```
templates/
    partials/
        your_plugin.html           ← the form / controls panel
        your_plugin_results.html   ← the results fragment (returned by routes)
```

---

## `manifest()`

```python
def manifest():
    return {
        "name":     "my_plugin",        # unique, snake_case
        "version":  "1.0",
        "provides": ["my.capability"],  # capabilities this plugin handles
        "requires": ["other.capability"], # capabilities this plugin calls
        "ui_defaults": {                # default form field values (optional)
            "symbol":   "BTC-USD",
            "interval": "5m",
        }
    }
```

**`ui_defaults`** — when the user navigates to your plugin, these values
pre-fill the form. If the user has submitted the form before, their last-used
values override these defaults (stored in the session). This means
`main.py` never needs to know your plugin's field names or defaults.

---

## `handle_request(request, context)`

Called by PluginHost when another plugin (or the UI) requests a capability.

### Request format

```python
request = {
    "capability": "my.capability",
    "payload": {
        "symbol": "BTC-USD",   # arbitrary input; always use .get() with defaults
    }
}
```

### Response format

```python
# Success
return {"status": "success", "data": <your output>}

# Error
return {"status": "error", "message": "Human-readable description"}
```

**Rules:**
- Never raise an unhandled exception — always return a response dict
- Always use `payload.get("key", default)` — never assume a key exists
- Wrap every `context.request()` call in try/except
- Check `response["status"]` before using `response["data"]`

---

## `get_ui_context(context)`

Called by the generic `GET /plugin/{name}` route when the user navigates
to your plugin. Return a dict of variables for your Jinja2 template.

The session-restored `ui_defaults` are merged in automatically as `ui`.
Your template accesses them as `{{ ui.symbol }}`, `{{ ui.interval }}`, etc.

```python
def get_ui_context(context):
    return {
        "interval_options": ["1m", "5m", "15m", "1h", "1d"],
        # anything your template needs beyond the restored form values
    }
```

Keep this lightweight — it runs every time the user clicks your plugin.

---

## `register_routes(app, templates, get_host)`

Register your plugin's HTTP routes directly onto the FastAPI app.
Called once at JagDash startup. **No changes to `main.py` needed.**

```python
def register_routes(app, templates, get_host):
    from fastapi import Form, Request
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext

    @app.post("/plugin/my_plugin/action", response_class=HTMLResponse)
    async def my_plugin_action(
        request:  Request,
        my_input: str = Form("default"),
    ):
        # Save state so the form restores on next visit
        request.session["ui_my_plugin"] = {"my_input": my_input}

        host    = get_host(request)
        context = PluginContext(host)

        try:
            result = context.request("my.capability", {"my_input": my_input})
        except Exception as e:
            return HTMLResponse(f'<div class="error-msg">{e}</div>')

        if result["status"] != "success":
            return HTMLResponse(f'<div class="error-msg">{result["message"]}</div>')

        return templates.TemplateResponse(
            request=request,
            name="partials/my_plugin_results.html",
            context={"data": result["data"], "error": None}
        )
```

**Standard signature:** always `(app, templates, get_host)`.

**Import FastAPI inside the function**, not at the top of the file.
This keeps the plugin's core logic free of web framework dependencies,
making it easier to test in isolation.

**Session state:** save submitted form values to `request.session["ui_{name}"]`
so they are restored the next time the user visits the plugin. The key must
match the pattern `ui_` + your plugin's manifest name.

---

## The `context` Object

Available in both `handle_request` and `register_routes` route handlers.

### `context.request(capability, payload)`

```python
try:
    response = context.request("market.price", {"symbol": "BTC-USD"})
except Exception as e:
    return {"status": "error", "message": f"market.price failed: {e}"}

if response["status"] != "success":
    return response   # propagate error

data = response["data"]
```

### `context.publish(event, payload)`

```python
context.publish("my.event.name", {"key": "value"})
```

Fire-and-forget. No return value. Call after your core logic succeeds.

---

## HTML Templates

Templates are Jinja2 files in `templates/partials/`.

**The UI panel** (`your_plugin.html`) is a fragment loaded into `#main-content`
when the user clicks your plugin in the sidebar. It is not a full HTML page —
no `<html>`, `<head>`, or `<body>` tags.

Use HTMX attributes to wire buttons to your routes:

```html
<form hx-post="/plugin/my_plugin/action"
      hx-target="#my-results"
      hx-swap="innerHTML"
      hx-indicator="#my-loading">

    <input type="text" name="my_input" value="{{ ui.my_input }}" class="text-input">
    <button type="submit" class="btn btn--primary">Run</button>
</form>

<div id="my-loading" class="htmx-indicator loading-inline">Working…</div>
<div id="my-results" class="results-area">
    <p class="placeholder-msg">Results appear here.</p>
</div>
```

Note `value="{{ ui.my_input }}"` — this restores the last-used value from
the session. `ui` is passed automatically by the `GET /plugin/{name}` route.

**The results fragment** (`your_plugin_results.html`) is returned by your
POST route and dropped into `#my-results` by HTMX.

---

## Capability Naming

```
domain.noun          # market.price
domain.noun.verb     # market.strategy.signal
```

### Signal vocabulary (trading signals only)

| Signal | Meaning |
|---|---|
| `BUY` | Bullish — price expected to rise |
| `SELL` | Bearish — price expected to fall |
| `HOLD` | Neutral / no edge |
| `WATCH` | Setup forming, direction unclear |

---

## Known Capabilities

| Capability | Plugin | Output |
|---|---|---|
| `market.price` | `market_data` | `list[{open, high, low, close, volume, date}]` |
| `market.settings` | `market_data` | `{symbol, interval, period}` |
| `market.strategy.signal` | `strategy_engine` | `{symbol, combined, signals, weights, market_meta}` |
| `news.search` | `news_scanner` | `list[article]` (NewsAPI format) |
| `news.signal` | `news_signal` | `{signal, bullish_total, bearish_total, articles}` |
| `news.headlines` | `news_feed` | `{headlines: [str]}` |
| `overview.summary` | `overview` | `{results: {market_price, strategy, news_signal, news_headlines}}` |
| `system.time` | `example_plugin` | `{timestamp, timezone}` |

---

## Checklist: New Plugin

- [ ] Plugin lives in `plugins/your_name/plugin.py`
- [ ] `manifest()` has all required keys: `name`, `version`, `provides`, `requires`
- [ ] `manifest()` has `ui_defaults` with default values for all form fields
- [ ] `name` is unique and snake_case
- [ ] All capabilities in `requires` are actually called in the code
- [ ] All capabilities in `provides` are handled in `handle_request()`
- [ ] `handle_request()` never raises; always returns success or error dict
- [ ] All `context.request()` calls are in try/except
- [ ] `register_routes()` imports `Request` from fastapi inside the function
- [ ] Route handlers save form values to `request.session["ui_{name}"]`
- [ ] Template at `templates/partials/your_name.html` exists
- [ ] Form fields use `value="{{ ui.field_name }}"` to restore last values
- [ ] Signal strings use the standard vocabulary (BUY/SELL/HOLD/WATCH)
- [ ] Plugin does not import other plugin files directly
- [ ] New dependencies added to `requirements.txt`

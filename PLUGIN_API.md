# PLUGIN_API.md
## JagDash Plugin API Reference

Version: 1.1

---

## Overview

JagDash uses a **mediator / hub-and-spoke architecture**.

Plugins do **not** communicate directly with one another.
All requests and events flow through `PluginHost`, which acts as the central router.

Think of it like a mixing board: every signal goes through the board, never from one instrument cable directly to another.

---

## Plugin File Structure

A plugin is a single Python file. It must implement:

| Function | Required | Purpose |
|---|---|---|
| `manifest()` | Yes | Declares plugin identity and capabilities |
| `handle_request(request, context)` | Yes | Handles incoming capability requests |
| `render_ui(context)` | No | Renders Streamlit UI for this plugin |

---

## `manifest()`

Returns a dict describing the plugin to the PluginHost.

```python
def manifest():
    return {
        "name": "my_plugin",        # unique string identifier, snake_case
        "version": "1.0",           # string
        "provides": [               # capabilities this plugin services
            "my.capability"
        ],
        "requires": [               # capabilities this plugin will call
            "other.capability"
        ]
    }
```

**Rules:**
- `name` must be unique across all loaded plugins
- `provides` and `requires` are lists of capability strings
- A plugin with an empty `requires` list is self-contained
- Capability strings use dot-notation: `domain.subdomain.action`

---

## `handle_request(request, context)`

Called by PluginHost when another plugin (or the UI) requests a capability this plugin provides.

### Request Format

```python
request = {
    "capability": "my.capability",   # which capability is being requested
    "payload": {                     # arbitrary dict of input parameters
        "symbol": "BTC-USD",
        "period": "6mo"
    }
}
```

**Rules:**
- Always use `request["payload"].get("key", default)` — never assume payload keys exist
- Unknown payload fields must be ignored, not rejected
- The `capability` field will always match one of your `provides` entries (PluginHost guarantees this)

### Response Format

Your function must return a dict in one of these two shapes:

**Success:**
```python
return {
    "status": "success",
    "data": <your output>    # any JSON-serializable value: dict, list, number, string
}
```

**Error:**
```python
return {
    "status": "error",
    "message": "Human-readable description of what went wrong"
}
```

**Rules:**
- Always return one of these two shapes — never raise an unhandled exception
- `data` can be any JSON-serializable type
- `message` should be descriptive enough for another developer to diagnose the problem
- Wrap risky operations (network calls, file I/O, parsing) in try/except and return error responses

### Handling Multiple Capabilities

If your plugin provides more than one capability, dispatch on the `capability` field:

```python
def handle_request(request, context):
    capability = request.get("capability")
    payload = request.get("payload", {})

    if capability == "my.capability.one":
        return handle_one(payload, context)
    elif capability == "my.capability.two":
        return handle_two(payload, context)
    else:
        return {
            "status": "error",
            "message": f"Unsupported capability: {capability}"
        }
```

---

## The `context` Object

`context` is passed into both `handle_request` and `render_ui`. It gives your plugin two powers:

### `context.request(capability, payload)`

Request data or an action from another plugin.

```python
response = context.request(
    "market.price",
    {"symbol": "BTC-USD"}
)

if response["status"] != "success":
    return response   # propagate the error upward

data = response["data"]
```

**Rules:**
- The capability you request must be listed in your manifest's `requires`
- Always check `response["status"]` before using `response["data"]`
- Wrap in try/except — the plugin providing the capability may not be loaded

```python
try:
    response = context.request("other.capability", payload)
except Exception as e:
    return {
        "status": "error",
        "message": f"Request to other.capability failed: {e}"
    }
```

### `context.publish(event, payload)`

Broadcast an event to any plugins or UI components listening for it.

```python
context.publish(
    "market.tick",
    {
        "symbol": "BTC-USD",
        "price": 97345.12
    }
)
```

**Rules:**
- Fire-and-forget: publish does not return a value
- Event names use dot-notation, same as capabilities
- Any plugin or UI component may subscribe to events — design payloads to be self-describing
- Publish after your core logic succeeds, not before

---

## `render_ui(context)` (Optional)

If your plugin has a user interface, implement this function using Streamlit.
JagDash calls it when rendering the plugin's panel.

```python
def render_ui(context):
    st.title("My Plugin")

    symbol = st.text_input("Symbol", "BTC-USD")

    if st.button("Run"):
        response = context.request(
            "my.capability",
            {"symbol": symbol}
        )

        if response["status"] == "success":
            st.success(f"Result: {response['data']}")
        else:
            st.error(response["message"])
```

**Rules:**
- Import `streamlit as st` at the top of your file
- Call `context.request()` the same way you would inside `handle_request()`
- Do not store state in global variables — use `st.session_state` for UI state

---

## Conventions

### Capability Naming

Use dot-separated lowercase strings. Follow this pattern:

```
domain.noun.verb
```

Examples:
- `market.price` — provide price data for a market symbol
- `market.strategy.signal` — provide a trading signal
- `portfolio.position.list` — list current portfolio positions
- `alert.price.set` — set a price alert

### Signal Vocabulary

Plugins that output trading signals must use this standard vocabulary:

| Signal | Meaning |
|---|---|
| `BUY` | Conditions favor a long entry |
| `SELL` | Conditions favor an exit or short |
| `HOLD` | No clear directional signal |
| `WATCH` | Noteworthy condition, no action implied |

Do not invent new signal strings. If your strategy produces a nuanced output, encode it in the `data` payload as metadata alongside a standard signal.

### Data Format for Time Series

When returning historical price data, use a list of dicts with lowercase column names:

```python
[
    {"close": 97200.00},
    {"close": 97450.50},
    ...
]
```

If you have full OHLCV data, include all fields:

```python
[
    {"open": 97100.0, "high": 97600.0, "low": 96900.0, "close": 97200.0, "volume": 12345},
    ...
]
```

Consumers should use `.get()` when reading these fields and handle missing columns gracefully.

---

## Checklist: New Plugin

Before submitting or loading a plugin, verify:

- [ ] `manifest()` is implemented and returns all four keys
- [ ] `name` is unique and snake_case
- [ ] All capabilities in `requires` are actually called in the code
- [ ] All capabilities in `provides` are actually handled in `handle_request`
- [ ] `handle_request` never raises an unhandled exception
- [ ] `handle_request` always returns `{"status": "success", ...}` or `{"status": "error", ...}`
- [ ] All `context.request()` calls are wrapped in try/except
- [ ] Signal strings use the standard vocabulary
- [ ] Plugin does not import other plugin files directly
- [ ] `requirements.txt` lists all third-party dependencies

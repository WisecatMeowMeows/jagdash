# JAGDASH_PLUGIN_SPEC.md
# JagDash Plugin Specification v1.1
# Mediator/hub-and-spoke architecture. Plugins never import each other.
# All communication routes through PluginHost.

---

## REQUIRED FUNCTIONS

### manifest() -> dict
```yaml
name: str          # unique, snake_case
version: str       # "1.0"
provides: [str]    # capability strings this plugin handles
requires: [str]    # capability strings this plugin calls via context.request()
```

### handle_request(request, context) -> dict
```yaml
request:
  capability: str        # matches one of manifest.provides
  payload: dict          # arbitrary input; always use .get(key, default)

response (success):
  status: "success"
  data: any              # JSON-serializable

response (error):
  status: "error"
  message: str           # human-readable, diagnostic
```
Rules:
- Never raise unhandled exceptions; catch all at boundary and return error response
- Wrap every context.request() in try/except
- Check response["status"] before using response["data"]
- If multiple provides, dispatch on request["capability"]

## OPTIONAL FUNCTIONS

### render_ui(context) -> None
- Streamlit UI only
- Call context.request() same as in handle_request()
- Use st.session_state for UI state; never global variables

---

## CONTEXT API

### context.request(capability: str, payload: dict) -> dict
- Calls the plugin that provides `capability`
- Returns same success/error envelope as handle_request
- Raises if no plugin provides that capability — always wrap in try/except

### context.publish(event: str, payload: dict) -> None
- Fire-and-forget broadcast; no return value
- Call after core logic succeeds, not before

---

## CONVENTIONS

### Capability naming
```
domain.noun          # market.price
domain.noun.verb     # market.strategy.signal
```

### Signal vocabulary (trading signals only)
```
BUY   SELL   HOLD   WATCH
```
No other signal strings. Encode nuance as metadata in data payload.

### Time series data format
```python
[{"close": float}, ...]                                    # minimum
[{"open": f, "high": f, "low": f, "close": f, "volume": i}, ...]  # full OHLCV
```
Consumers use .get(); handle missing columns gracefully.

---

## KNOWN PLUGINS (capability registry)

| Capability | Plugin | Output |
|---|---|---|
| `market.price` | `market_data` | `list[{"close": float}]` ~126 daily candles via yfinance |
| `market.strategy.signal` | `strategy_engine` | `{"symbol": str, "strategy": str, "signal": BUY\|SELL\|HOLD\|WATCH}` |

Published events:
- `market.tick` — `{"symbol": str, "price": float}` — emitted by market_data
- `strategy.signal.generated` — `{"symbol": str, "strategy": str, "signal": str}` — emitted by strategy_engine

---

## ENVIRONMENT

```bash
python -m venv jagdash_env
source jagdash_env/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```
Always use `python -m pip install` (not bare pip). Always launch streamlit from inside active venv.

Base requirements: streamlit, pandas, numpy, yfinance

---

## CHECKLIST

- [ ] manifest() has all four keys; name is unique and snake_case
- [ ] Every provides string is handled in handle_request()
- [ ] Every requires string is actually called in code
- [ ] handle_request() never raises; always returns success or error envelope
- [ ] Every context.request() is in try/except
- [ ] Signal strings use standard vocabulary
- [ ] No direct imports of other plugin files
- [ ] New dependencies added to requirements.txt

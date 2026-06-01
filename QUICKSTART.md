# QUICKSTART.md
## Building Your First JagDash Plugin

This guide walks you through creating a working plugin from scratch.
By the end you will have a plugin loaded in JagDash that provides a real capability.

---

## Before You Start

Make sure you have the reference files:

| File | Purpose |
|---|---|
| `PLUGIN_API.md` | Full API contract — the authoritative reference |
| `ARCHITECTURE.md` | System design and known plugins |
| `plugin_template.py` | Starter template — copy this for every new plugin |
| `example_plugin.py` | Minimal working example to study |
| `requirements.txt` | Base dependencies |

---

## Step 1 — Set Up the Environment

```bash
# Create and activate the virtual environment
python -m venv jagdash_env
source jagdash_env/bin/activate        # macOS / Linux
# jagdash_env\Scripts\activate         # Windows

# Install base dependencies
python -m pip install -r requirements.txt
```

Always activate the venv before working. Always use `python -m pip install`, not bare `pip install`.

---

## Step 2 — Decide What Your Plugin Does

Answer these questions before writing any code:

**What capability does it provide?**
Name it using dot-notation: `domain.noun` or `domain.noun.verb`.
Example: `portfolio.summary`, `alert.price.check`, `news.sentiment`

**What does it need from other plugins?**
Look at `ARCHITECTURE.md` → Known Plugins to see what's available.
If you need price data, you can call `market.price`.

**What does it return?**
Define the shape of your `data` payload before you write the logic.

---

## Step 3 — Copy the Template

```bash
cp plugin_template.py plugins/my_plugin.py
```

Then open `plugins/my_plugin.py` and replace all `TODO` markers:

1. Set `PLUGIN_NAME` to a human-readable name
2. Set `manifest()` → `name` to a unique snake_case string
3. Set `manifest()` → `provides` to your capability string(s)
4. Set `manifest()` → `requires` to any capabilities you'll call
5. Replace the dispatch in `handle_request()` to match your capability string
6. Fill in `_handle_my_capability()` with real logic
7. Update `render_ui()` inputs and output display

---

## Step 4 — Implement the Logic

A plugin that calls another plugin:

```python
def _handle_my_capability(payload, context):
    symbol = payload.get("symbol", "BTC-USD")

    # 1. Call a required capability
    try:
        response = context.request("market.price", {"symbol": symbol})
    except Exception as e:
        return {"status": "error", "message": f"market.price failed: {e}"}

    if response["status"] != "success":
        return response

    data = response["data"]

    # 2. Do your work
    result = your_logic_here(data)

    # 3. Return success
    return {
        "status": "success",
        "data": {"symbol": symbol, "result": result}
    }
```

A self-contained plugin (no requires):

```python
def _handle_my_capability(payload, context):
    input_value = payload.get("my_input", "default")

    try:
        result = your_logic_here(input_value)
    except Exception as e:
        return {"status": "error", "message": f"Processing failed: {e}"}

    return {
        "status": "success",
        "data": {"result": result}
    }
```

---

## Step 5 — Add Dependencies

If your plugin uses any third-party libraries, add them to `requirements.txt`:

```
my_new_library
```

Then install:

```bash
python -m pip install -r requirements.txt
```

---

## Step 6 — Test It

Restart JagDash to pick up the new plugin:

```bash
streamlit run app.py
```

Find your plugin's panel in the dashboard and click your button.

If something goes wrong:
- Check the terminal for Python tracebacks
- Add `st.write(f"DEBUG: {variable}")` inside `render_ui()` to inspect values
- Check that all `requires` capabilities are provided by loaded plugins

---

## Common Mistakes

**"local variable referenced before assignment"**
A `context.request()` call threw an exception before the result was assigned.
Wrap it in try/except — see Step 4 above.

**"Need at least N candles" or similar data errors**
The plugin providing your data returned less than you expected.
Add a debug line to see how much data arrived: `st.write(f"Got {len(data)} rows")`

**Plugin not appearing in JagDash**
Check that `manifest()` returns all four required keys.
Check that the file is in the plugins directory JagDash scans.

**"Unsupported capability"**
Your `handle_request()` dispatch doesn't match the string in your `manifest()` provides list exactly.

**Package not found at runtime**
You installed it outside the venv. Use `python -m pip install` with the venv active.

---

## Giving Context to an AI Assistant

If you use an AI to help build a plugin, paste these files at the start of the conversation:

1. `PLUGIN_API.md`
2. `ARCHITECTURE.md`
3. `plugin_template.py`
4. Any existing plugin your new plugin will call (so the AI knows the data format)

Then describe what your plugin should do and ask it to fill in the template.

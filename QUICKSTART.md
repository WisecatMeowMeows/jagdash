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

**What form fields does its UI need?**
List them — these go in `ui_defaults` in `manifest()`.

---

## Step 3 — Create the Plugin Directory and Copy the Template

```bash
mkdir plugins/my_plugin
cp plugin_template.py plugins/my_plugin/plugin.py
```

Then open `plugins/my_plugin/plugin.py` and replace all `TODO` markers:

1. Set `PLUGIN_NAME` to a human-readable name
2. Set `manifest()` → `name` to a unique snake_case string
3. Set `manifest()` → `provides` to your capability string(s)
4. Set `manifest()` → `requires` to any capabilities you'll call
5. Set `manifest()` → `ui_defaults` to your form field defaults
6. Replace the dispatch in `handle_request()` to match your capability string
7. Fill in `_handle_my_capability()` with real logic
8. Update `register_routes()` with your route path and form fields

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

## Step 5 — Create the UI Templates

Create two files in `templates/partials/`:

**`templates/partials/my_plugin.html`** — the controls panel:

```html
<div class="plugin-panel">
    <div class="plugin-header">
        <h2>My Plugin</h2>
        <p class="plugin-subtitle">What it does</p>
    </div>

    <form class="plugin-controls"
          hx-post="/plugin/my_plugin/action"
          hx-target="#my-results"
          hx-swap="innerHTML"
          hx-indicator="#my-loading">

        <div class="controls-row">
            <div class="control-group">
                <label for="my-input">Input</label>
                <input type="text" id="my-input" name="my_input"
                       value="{{ ui.my_input }}" class="text-input">
            </div>
            <div class="control-group control-group--btn">
                <label>&nbsp;</label>
                <button type="submit" class="btn btn--primary">Run</button>
            </div>
        </div>

    </form>

    <div id="my-loading" class="htmx-indicator loading-inline">Working…</div>
    <div id="my-results" class="results-area">
        <p class="placeholder-msg">Results appear here.</p>
    </div>
</div>
```

**`templates/partials/my_plugin_results.html`** — what gets swapped in:

```html
{% if error %}
<div class="error-msg">{{ error }}</div>
{% else %}
<div class="results-content">
    <p>{{ data.result }}</p>
</div>
{% endif %}
```

Note `value="{{ ui.my_input }}"` — this restores the last submitted value.
`ui` is provided automatically from the session + `ui_defaults`.

---

## Step 6 — Add Dependencies

If your plugin uses any third-party libraries, add them to `requirements.txt`:

```
my_new_library
```

Then install:

```bash
python -m pip install -r requirements.txt
```

---

## Step 7 — Test It

Restart JagDash to pick up the new plugin:

```bash
uvicorn main:app --reload --port 8000
```

Your plugin appears in the sidebar automatically. Click it and test.

If something goes wrong:
- Check the terminal for Python tracebacks — uvicorn prints the full error
- Check the browser developer console (F12) for JavaScript/HTMX errors
- Check the Network tab in dev tools to see the HTTP request and response
- Verify `manifest()` returns all required keys
- Verify `register_routes()` imports `Request` from fastapi inside the function
- Check that all `requires` capabilities are provided by loaded plugins

---

## Common Mistakes

**422 Unprocessable Entity on form submit**
FastAPI can't parse the form. Most common cause: `request` parameter in the
route handler has the wrong type annotation. Must be `request: Request`
(importing `Request` from fastapi inside `register_routes`), not `request: object`.

**"local variable referenced before assignment"**
A `context.request()` call threw an exception before the result was assigned.
Wrap it in try/except — see Step 4 above.

**Plugin not appearing in JagDash**
Check that `manifest()` returns all required keys (`name`, `version`,
`provides`, `requires`). Check that the file is at `plugins/name/plugin.py`.

**"Unsupported capability"**
Your `handle_request()` dispatch doesn't match the string in `manifest()` provides exactly.

**Form values not restoring after navigation**
Check that `request.session["ui_my_plugin"] = {...}` uses the exact plugin
name from `manifest()["name"]`. Check that form fields use `value="{{ ui.field_name }}"`.

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

# plugin_template.py — JagDash Plugin Template
#
# HOW TO USE:
#   1. Create a new folder:  plugins/your_plugin_name/
#   2. Copy this file to:    plugins/your_plugin_name/plugin.py
#   3. Replace all TODO markers
#   4. Create the UI template: templates/partials/your_plugin_name.html
#   5. Create the results template: templates/partials/your_plugin_name_results.html
#   6. Restart JagDash — your plugin appears automatically
#
# No changes to main.py are needed. Routes are registered by register_routes().

# TODO: import libraries your plugin needs for its logic
# DO NOT import streamlit — the UI layer is handled by FastAPI + Jinja2


# ---------------------------------------------------------------------------
# Plugin identity
# ---------------------------------------------------------------------------

PLUGIN_NAME = "My Plugin"   # TODO: human-readable name


# ---------------------------------------------------------------------------
# Required: manifest()
# ---------------------------------------------------------------------------

def manifest():
    return {
        "name":     "my_plugin",        # TODO: unique snake_case identifier
        "version":  "1.0",
        "provides": ["my.capability"],  # TODO: capability strings this plugin handles
        "requires": [
            # "other.capability"        # TODO: capabilities you call via context.request()
            # Delete this section if self-contained
        ],
        "ui_defaults": {
            # TODO: default values for your form fields.
            # These are restored when the user navigates to your plugin.
            # Keys must match the form field names in your HTML template.
            # Example:
            # "symbol":   "BTC-USD",
            # "interval": "5m",
        }
    }


# ---------------------------------------------------------------------------
# Required: handle_request()
# ---------------------------------------------------------------------------

def handle_request(request, context):
    """
    Called by PluginHost when a capability this plugin provides is requested.
    Always returns {"status": "success", "data": ...}
                or {"status": "error",   "message": ...}
    Never raises an unhandled exception.
    """
    capability = request.get("capability")
    payload    = request.get("payload", {})

    if capability == "my.capability":       # TODO: match your capability string
        return _handle_my_capability(payload, context)

    return {"status": "error", "message": f"Unsupported capability: {capability}"}


def _handle_my_capability(payload, context):
    # Read inputs — always use .get() with a default
    my_input = payload.get("my_input", "default")   # TODO: your parameters

    # Call another plugin if needed (only if listed in manifest requires):
    # try:
    #     response = context.request("other.capability", {"key": "value"})
    # except Exception as e:
    #     return {"status": "error", "message": f"other.capability failed: {e}"}
    # if response["status"] != "success":
    #     return response
    # data = response["data"]

    # Your logic here
    try:
        result = my_input.upper()   # TODO: replace with real logic
    except Exception as e:
        return {"status": "error", "message": f"Processing failed: {e}"}

    # Publish an event (optional)
    # context.publish("my.event", {"result": result})

    return {
        "status": "success",
        "data": {"result": result}   # TODO: your output structure
    }


# ---------------------------------------------------------------------------
# Optional: get_ui_context()
# Called when the user navigates to your plugin. Return any data your
# HTML template needs beyond the session-restored ui_defaults.
# ---------------------------------------------------------------------------

def get_ui_context(context):
    """
    Return a dict of variables for templates/partials/my_plugin.html.
    Keep this lightweight — it runs every time the user clicks your plugin.
    The 'ui' variable (session state) is merged in automatically by main.py.
    """
    return {
        # "some_list": ["option1", "option2"],  # e.g. dropdown options
    }


# ---------------------------------------------------------------------------
# Optional: register_routes()
# Register this plugin's HTTP routes onto the FastAPI app.
# Called once at startup. No changes to main.py needed.
# ---------------------------------------------------------------------------

def register_routes(app, templates, get_host):
    """
    Register POST routes for this plugin's UI actions.

    Standard signature — always these three arguments:
        app        — FastAPI app instance
        templates  — Jinja2Templates instance
        get_host   — function(request) -> PluginHost
    """
    from fastapi import Form, Request
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext

    @app.post("/plugin/my_plugin/action", response_class=HTMLResponse)  # TODO: rename
    async def my_plugin_action(
        request:  Request,
        my_input: str = Form("default"),   # TODO: your form fields
    ):
        # Save state so the form restores values on next visit
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
            name="partials/my_plugin_results.html",   # TODO: rename
            context={"data": result["data"], "error": None}
        )

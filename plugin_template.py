# plugin_template.py — JagDash Plugin Template
#
# Copy this file to plugins/your_plugin_name/plugin.py
# Replace all TODO markers.
# Add your template to templates/partials/your_plugin_name.html
# Add your routes to main.py

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
        ]
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

    # Call another plugin if needed (only if listed in manifest requires)
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
# Called by the generic /plugin/{name} route in main.py to pass
# data into the Jinja2 template at templates/partials/my_plugin.html
# ---------------------------------------------------------------------------

def get_ui_context(context):
    """
    Return a dict of variables for the plugin's Jinja2 template.
    Keep this lightweight — it runs every time the user navigates to this plugin.
    """
    return {
        "some_default": "value",    # TODO: whatever your template needs
    }


# ---------------------------------------------------------------------------
# NOTE: No render_ui() function.
# In JagDash FastAPI, the UI is defined in:
#   templates/partials/my_plugin.html      (the form / controls)
#   templates/partials/my_plugin_results.html  (the results fragment)
#
# Routes in main.py handle form submissions and call handle_request().
# See existing plugins for examples.
# ---------------------------------------------------------------------------

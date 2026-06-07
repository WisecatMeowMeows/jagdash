# example_plugin.py — JagDash Example Plugin: System Clock
#
# The simplest possible working plugin.
# No requires, one capability, one route.
#
# To use this as a real plugin:
#   1. Copy to plugins/system_clock/plugin.py
#   2. Create templates/partials/system_clock.html  (see comment at bottom)
#   3. Restart JagDash — the plugin appears in the sidebar automatically
#
# No changes to main.py are needed. register_routes() handles that.

from datetime import datetime, timezone


PLUGIN_NAME = "System Clock"


def manifest():
    return {
        "name":     "system_clock",
        "version":  "1.0",
        "provides": ["system.time"],
        "requires": [],
        "ui_defaults": {}   # no form fields to restore for this plugin
    }


def handle_request(request, context):
    capability = request.get("capability")
    payload    = request.get("payload", {})

    if capability == "system.time":
        return _handle_system_time(payload, context)

    return {"status": "error", "message": f"Unsupported capability: {capability}"}


def _handle_system_time(payload, context):
    tz_name = payload.get("timezone", "UTC")
    try:
        now       = datetime.now(timezone.utc)
        timestamp = now.isoformat()
    except Exception as e:
        return {"status": "error", "message": f"Failed to get time: {e}"}

    context.publish("system.time.checked", {"timestamp": timestamp})

    return {
        "status": "success",
        "data": {"timestamp": timestamp, "timezone": tz_name}
    }


def get_ui_context(context):
    return {}   # no initial data needed — template is fully static


def register_routes(app, templates, get_host):
    """
    Register this plugin's routes.
    Called once at startup by main.py. No edits to main.py needed.
    """
    from fastapi import Request
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext

    @app.post("/plugin/system_clock/time", response_class=HTMLResponse)
    async def system_clock_time(request: Request):
        host   = get_host(request)
        ctx    = PluginContext(host)
        result = ctx.request("system.time", {})
        if result["status"] == "success":
            ts = result["data"]["timestamp"]
            return HTMLResponse(f'<div class="success-msg">{ts}</div>')
        return HTMLResponse(f'<div class="error-msg">{result["message"]}</div>')


# ---------------------------------------------------------------------------
# templates/partials/system_clock.html would look like this:
#
#   <div class="plugin-panel">
#       <div class="plugin-header">
#           <h2>System Clock</h2>
#           <p class="plugin-subtitle">Current UTC time</p>
#       </div>
#       <form hx-post="/plugin/system_clock/time"
#             hx-target="#clock-result"
#             hx-swap="innerHTML">
#           <button type="submit" class="btn btn--primary">Get Time</button>
#       </form>
#       <div id="clock-result" class="results-area">
#           <p class="placeholder-msg">Click to get current time.</p>
#       </div>
#   </div>
# ---------------------------------------------------------------------------

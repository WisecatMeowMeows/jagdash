# example_plugin.py — JagDash Example Plugin: System Clock
#
# The simplest possible working plugin. No requires, one capability.
# Use this as a structural reference.
#
# To make this appear in JagDash:
#   1. Copy to plugins/system_clock/plugin.py
#   2. Create templates/partials/system_clock.html
#   3. Add a POST route in main.py for the button action

from datetime import datetime, timezone


PLUGIN_NAME = "System Clock"


def manifest():
    return {
        "name":     "system_clock",
        "version":  "1.0",
        "provides": ["system.time"],
        "requires": []
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
    """Data for templates/partials/system_clock.html"""
    return {}   # This plugin needs no initial data — form is static


# ---------------------------------------------------------------------------
# The HTML template would be templates/partials/system_clock.html:
#
#   <div class="plugin-panel">
#       <div class="plugin-header"><h2>System Clock</h2></div>
#       <form hx-post="/plugin/system_clock/time"
#             hx-target="#clock-result" hx-swap="innerHTML">
#           <button type="submit" class="btn btn--primary">Get Time</button>
#       </form>
#       <div id="clock-result" class="results-area"></div>
#   </div>
#
# And in main.py:
#
#   @app.post("/plugin/system_clock/time", response_class=HTMLResponse)
#   async def system_clock_time(request: Request):
#       host   = get_host(request)
#       ctx    = PluginContext(host)
#       result = ctx.request("system.time", {})
#       if result["status"] == "success":
#           ts = result["data"]["timestamp"]
#           return HTMLResponse(f'<div class="success-msg">{ts}</div>')
#       return HTMLResponse(f'<div class="error-msg">{result["message"]}</div>')
# ---------------------------------------------------------------------------

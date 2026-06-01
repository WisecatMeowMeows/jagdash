# example_plugin.py
# JagDash Example Plugin: System Clock
#
# This is the simplest possible working plugin.
# It has no requires — it depends on nothing else.
# It provides one capability: "system.time"
#
# Use this as a reference for structure and patterns.
# It is safe to load and run without any other plugins present.

import streamlit as st
from datetime import datetime, timezone


PLUGIN_NAME = "System Clock"


# ---------------------------
# Required: manifest()
# ---------------------------

def manifest():
    return {
        "name": "system_clock",
        "version": "1.0",
        "provides": [
            "system.time"
        ],
        "requires": []          # self-contained — calls nothing else
    }


# ---------------------------
# Required: handle_request()
# ---------------------------

def handle_request(request, context):
    capability = request.get("capability")
    payload = request.get("payload", {})

    if capability == "system.time":
        return _handle_system_time(payload, context)

    return {
        "status": "error",
        "message": f"Unsupported capability: {capability}"
    }


def _handle_system_time(payload, context):
    # Read optional input — default to UTC if not specified
    tz_name = payload.get("timezone", "UTC")

    try:
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to get system time: {e}"
        }

    # Publish event so any listener can react to a time check
    context.publish(
        "system.time.checked",
        {"timestamp": timestamp}
    )

    return {
        "status": "success",
        "data": {
            "timestamp": timestamp,
            "timezone": tz_name
        }
    }


# ---------------------------
# Optional: render_ui()
# ---------------------------

def render_ui(context):
    st.title(PLUGIN_NAME)

    if st.button("Get Current Time"):
        response = context.request(
            "system.time",
            {"timezone": "UTC"}
        )

        if response["status"] == "success":
            data = response["data"]
            st.success(data["timestamp"])
        else:
            st.error(response["message"])

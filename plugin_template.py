# plugin_template.py
# JagDash Plugin Template
#
# Instructions:
# 1. Copy this file to plugins/your_plugin_name.py
# 2. Replace all placeholder values (marked with TODO)
# 3. Remove comments you no longer need
# 4. Add your dependencies to requirements.txt

import streamlit as st

# TODO: import any additional libraries your plugin needs
# Example: import pandas as pd


# ---------------------------
# Plugin Identity
# ---------------------------

PLUGIN_NAME = "My Plugin"  # TODO: human-readable name for UI display


# ---------------------------
# Required: manifest()
# ---------------------------

def manifest():
    return {
        "name": "my_plugin",            # TODO: unique snake_case identifier
        "version": "1.0",
        "provides": [
            "my.capability"             # TODO: capability strings this plugin handles
        ],
        "requires": [
            # "other.capability"        # TODO: list capabilities you will call via context.request()
            #                           # Delete this section if your plugin is self-contained
        ]
    }


# ---------------------------
# Required: handle_request()
# ---------------------------

def handle_request(request, context):
    """
    Called by PluginHost when another plugin or the UI requests
    a capability this plugin provides.

    Always return either:
        {"status": "success", "data": <your output>}
        {"status": "error",   "message": "<description>"}
    """

    capability = request.get("capability")
    payload = request.get("payload", {})

    # --- Dispatch on capability ---
    if capability == "my.capability":           # TODO: match your capability string
        return _handle_my_capability(payload, context)

    # If we get here, PluginHost sent us something we don't handle
    return {
        "status": "error",
        "message": f"Unsupported capability: {capability}"
    }


def _handle_my_capability(payload, context):
    """
    Core logic for my.capability.
    Separate function keeps handle_request() clean.
    """

    # --- Read inputs from payload ---
    # Always use .get() with a default — never assume a key exists
    symbol = payload.get("symbol", "BTC-USD")   # TODO: replace with your parameters

    # --- Call other plugins if needed ---
    # Only do this if "other.capability" is in your manifest requires list
    #
    # try:
    #     response = context.request(
    #         "other.capability",
    #         {"key": "value"}
    #     )
    # except Exception as e:
    #     return {
    #         "status": "error",
    #         "message": f"Request to other.capability failed: {e}"
    #     }
    #
    # if response["status"] != "success":
    #     return response
    #
    # data = response["data"]

    # --- Your logic here ---
    # TODO: replace with real implementation
    result = f"Processed: {symbol}"

    # --- Publish an event (optional) ---
    # Notify any listeners that something happened
    # context.publish(
    #     "my.event.name",
    #     {"key": "value"}
    # )

    # --- Return success ---
    return {
        "status": "success",
        "data": {
            "symbol": symbol,
            "result": result    # TODO: replace with your output structure
        }
    }


# ---------------------------
# Optional: render_ui()
# ---------------------------

def render_ui(context):
    """
    Streamlit UI for this plugin.
    Remove this function entirely if your plugin has no UI.
    """

    st.title(PLUGIN_NAME)

    # --- Inputs ---
    symbol = st.text_input("Symbol", value="BTC-USD")  # TODO: your inputs

    # --- Trigger ---
    if st.button("Run"):
        response = context.request(
            "my.capability",            # TODO: match your capability string
            {
                "symbol": symbol        # TODO: match your payload keys
            }
        )

        # --- Display results ---
        if response["status"] == "success":
            data = response["data"]
            st.success(f"Result: {data['result']}")  # TODO: display your output
            st.json(data)                            # useful during development, remove later

        else:
            st.error(response["message"])

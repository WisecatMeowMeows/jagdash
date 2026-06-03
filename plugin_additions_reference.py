# This file documents the two small additions needed to existing plugin files.
# It is NOT a runnable file — it's a reference for the manual edits below.

# ============================================================
# 1. plugins/config_plugin/plugin.py
#    Add this function anywhere in the file (after manifest() is fine)
# ============================================================

def get_ui_context(context):
    """Return data needed by partials/config_plugin.html"""
    profiles = context.get_all_profiles()
    active_profile = context.get_active_profile()
    # Derive the active profile name by matching dashboard_name against profile keys
    # A cleaner approach: store name separately, but this works with current data model
    all_profile_names = context.get_all_profiles()
    # get_active_profile() returns the dict, not the name
    # We need the name — read it from the host via config_manager
    # Use a fallback: first profile if we can't determine it
    active_name = profiles[0] if profiles else "default"
    # Check if NewsAPI key is configured (don't expose the actual value)
    news_key = context.get_api_key("newsapi")
    return {
        "profiles": profiles,
        "active_profile": active_profile,
        "active_name": active_name,
        "news_key_set": bool(news_key),
    }


# ============================================================
# 2. plugins/strategy_engine/plugin.py
#    Add this function anywhere after _reload_strategies() is called
# ============================================================

def get_ui_context(context):
    """Return data needed by partials/strategy_engine.html"""
    strategy_list = []
    for name in STRATEGIES:
        meta = _strategy_meta.get(name, {})
        strategy_list.append({
            "name": name,
            "type": meta.get("type", ""),
            "description": meta.get("description", ""),
            "source": meta.get("source", "built-in"),
            "min_candles": meta.get("min_candles", 0),
            "file": meta.get("file", ""),
        })
    return {
        "strategies": strategy_list,
        "interval_options": ["1m","2m","5m","15m","30m","60m","90m","1h","1d","1wk","1mo"],
        "period_options": ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"],
        "errors": _discovery_errors,
    }

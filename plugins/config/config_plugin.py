# plugins/config_plugin/plugin.py — Streamlit removed
# render_ui() deleted. All config logic now in main.py routes.
# get_ui_context() provides data to the Jinja2 template.

#plugin_dir = "plugins"

def manifest():
    return {
        "name":     "config",
        "version":  "1.1",
        "provides": [],
        "requires": []
    }


def get_ui_context(context):
    from theme_engine import get_theme, preset_names
    profiles       = context.get_all_profiles()
    active_profile = context.get_active_profile()
    active_name    = profiles[0] if profiles else "default"
    news_key       = context.get_api_key("newsapi")
    cmc_key        = context.get_api_key("coinmarketcap")
    theme          = get_theme(active_profile)
    return {
        "profiles":       profiles,
        "active_profile": active_profile,
        "active_name":    active_name,
        "news_key_set":   bool(news_key),
        "cmc_key_set":    bool(cmc_key),
        "theme":          theme,
        "preset_names":   preset_names(),
     #   "plugin_dir":     plugin_dir
    }

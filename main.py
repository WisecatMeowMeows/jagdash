"""
main.py — JagDash FastAPI entry point

To run:
    uvicorn main:app --reload --port 8000
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from typing import List, Optional
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware

from host import PluginHost
from plugin_loader import load_plugins
from plugin_context import PluginContext
from theme_engine import (
    get_theme, generate_css, get_preset,
    preset_names as get_preset_names, PRESETS
)

# Use explicit path so .env is found regardless of which directory
# uvicorn is launched from. __file__ is always main.py's location.
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# UI_DEFAULTS has been removed.
# Each plugin now declares its own defaults in manifest()["ui_defaults"].
# get_plugin_state() reads from there automatically.


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    host = PluginHost()
    plugins = load_plugins()
    for plugin in plugins:
        host.register_plugin(plugin)
    missing = host.validate_dependencies()
    if missing:
        print("WARNING: Unmet plugin dependencies:")
        for m in missing:
            print(f"  {m['plugin']} requires '{m['missing']}' — not loaded")
    app.state.host = host

    # Startup key diagnostics — tells you immediately if .env loaded correctly.
    # Shows "set" or "NOT SET" without revealing the actual key values.
    from pathlib import Path as _Path
    dotenv_file = _Path(__file__).parent / ".env"
    print(f"  .env file: {'found' if dotenv_file.exists() else 'NOT FOUND — check path'}")
    for _svc, _var in [("newsapi", "NEWSAPI_KEY"), ("coinmarketcap", "COINMARKETCAP_KEY"),
                        ("session", "SESSION_SECRET")]:
        _val = os.getenv(_var, "")
        print(f"  {_var}: {'set (' + str(len(_val)) + ' chars)' if _val else 'NOT SET'}")

    # Call register_routes() on any plugin that defines it.
    # This lets plugins own their own POST routes rather than requiring
    # main.py to know about every plugin's form fields.
    # Plugins that haven't migrated yet (no register_routes) are unaffected.
    for plugin_name, plugin_data in host.plugins.items():
        plugin_module = plugin_data["module"]
        if hasattr(plugin_module, "register_routes"):
            try:
                plugin_module.register_routes(app, templates, get_host)
                print(f"  routes registered: {plugin_name}")
            except Exception as e:
                print(f"  WARNING: {plugin_name}.register_routes() failed: {e}")

    print(f"JagDash started. Loaded plugins: {host.list_plugins()}")
    yield
    print("JagDash shutting down.")


# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="JagDash", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "jagdash-dev-secret-change-in-production"),
    session_cookie="jagdash_session",
    max_age=86400 * 7,
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount images/ directory so /images/filename.jpg is served directly.
# StaticFiles will raise an error at startup if the directory doesn't exist,
# so we create it if missing rather than crashing.
import pathlib
pathlib.Path("images").mkdir(exist_ok=True)
app.mount("/images", StaticFiles(directory="images"), name="images")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_host(request: Request) -> PluginHost:
    return request.app.state.host


def get_plugin_state(request: Request, plugin_name: str) -> dict:
    """
    Return the UI state for a plugin, merging in order:
      1. Plugin's own manifest ui_defaults  (lowest priority)
      2. Session-saved values from last submit  (highest priority)

    Plugins declare their defaults in manifest():
        "ui_defaults": {"symbol": "BTC-USD", "interval": "5m"}

    This means main.py never needs to know a plugin's field names or defaults.
    """
    host = request.app.state.host
    try:
        manifest = host.plugins[plugin_name]["manifest"]
        defaults = manifest.get("ui_defaults", {})
    except (KeyError, AttributeError):
        defaults = {}
    saved = request.session.get(f"ui_{plugin_name}", {})
    return {**defaults, **saved}


def save_plugin_state(request: Request, plugin_name: str, values: dict) -> None:
    request.session[f"ui_{plugin_name}"] = values


def base_context(request: Request) -> dict:
    """
    Build the context dict needed by base.html on full page loads.
    theme_css_content is the raw CSS inside <style id="jagdash-theme">.
    logo_path is normalized to an absolute URL so src= works from any page.
    """
    host    = get_host(request)
    profile = host.get_active_profile()
    theme   = get_theme(profile)
    from theme_engine import generate_css, normalize_asset_path
    raw_logo = profile.get("logo_path", "").strip()
    return {
        "dashboard_name":    profile.get("dashboard_name", "JagDash"),
        "plugins":           host.list_plugins(),
        "theme_css_content": generate_css(theme),
        "logo_path":         normalize_asset_path(raw_logo) if raw_logo else "",
    }


def success_fragment(message: str) -> HTMLResponse:
    return HTMLResponse(f'<div class="success-msg">{message}</div>')

def error_fragment(message: str) -> HTMLResponse:
    return HTMLResponse(f'<div class="error-msg">{message}</div>')


# ---------------------------------------------------------------------------
# CORE ROUTES
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="base.html", context=base_context(request)
    )


@app.get("/plugin/{plugin_name}", response_class=HTMLResponse)
async def load_plugin(request: Request, plugin_name: str):
    host = get_host(request)
    if plugin_name not in host.plugins:
        return HTMLResponse(
            content=f'<div class="error-msg">Plugin "{plugin_name}" not found.</div>',
            status_code=404
        )
    plugin_module = host.plugins[plugin_name]["module"]
    context       = PluginContext(host)
    ui_context    = {}
    if hasattr(plugin_module, "get_ui_context"):
        try:
            ui_context = plugin_module.get_ui_context(context)
        except Exception as e:
            return HTMLResponse(
                content=f'<div class="error-msg">Plugin "{plugin_name}" context failed: {e}</div>',
                status_code=500
            )
    ui_state = get_plugin_state(request, plugin_name)
    try:
        return templates.TemplateResponse(
            request=request,
            name=f"partials/{plugin_name}.html",
            context={"plugin_name": plugin_name, "ui": ui_state, **ui_context}
        )
    except Exception:
        return HTMLResponse(
            content=f'<div class="plugin-no-ui"><p>Plugin <strong>{plugin_name}</strong> has no UI panel.</p></div>'
        )

@app.post("/plugin/c0rdin8/fetch_all")
async def c0rdin8_fetch_all(request: Request):

    host = get_host(request)
    context = PluginContext(host)

    result = context.request("feed.fetch_all", {})

    return templates.TemplateResponse(
        request=request,
        name="partials/c0rdin8_results.html",
        context={
            "signals": result["data"],
            "feed": {
                "feed_name": "All Feeds",
                "publisher": "",
                "signal_count": len(result["data"])
            },
            "error": None
        }
    )
    
# ---------------------------------------------------------------------------
# OOB STYLE REFRESH HELPER
# After saving theme, we return the feedback message plus an OOB swap
# that updates the <style> block in <head>.
# We include a full-page reload trigger instead — simpler and reliable,
# since the theme affects the layout itself (sidebar width, spacing).
# ---------------------------------------------------------------------------

def theme_saved_response(message: str, profile: dict) -> HTMLResponse:
    """
    Update the theme in-place using HTMX out-of-band swap.

    Returns two things in one response:
      1. A feedback message for #config-feedback (the normal hx-target)
      2. A new <style> block with hx-swap-oob="true" and id="jagdash-theme"
         HTMX finds the existing <style id="jagdash-theme"> in the page and
         replaces it with the new CSS — no page reload, no navigation.

    Note: sidebar-width and spacing changes take effect immediately because
    CSS custom properties update live when the <style> block changes.
    The browser re-renders affected elements automatically.
    """
    from theme_engine import get_theme, generate_css
    theme   = get_theme(profile)
    new_css = generate_css(theme)
    # The OOB element must have the same id as the element in the page
    oob_style = f'<style id="jagdash-theme" hx-swap-oob="true">{new_css}</style>'
    feedback  = f'<div class="success-msg">{message}</div>'
    return HTMLResponse(feedback + oob_style)


# ---------------------------------------------------------------------------
# MARKET DATA — routes moved to plugins/market_data/plugin.py
# register_routes() is called automatically at startup.
# ---------------------------------------------------------------------------

@app.post("/plugin/c0rdin8/fetch", response_class=HTMLResponse)
async def c0rdin8_fetch(
    request: Request,
    feed_url: str = Form(...)
):

    save_plugin_state(
        request,
        "c0rdin8",
        {"feed_url": feed_url}
    )

    host = get_host(request)
    context = PluginContext(host)

    try:

        result = context.request(
            "feed.fetch",
            {
                "feed_url": feed_url
            }
        )

    except Exception as e:

        return templates.TemplateResponse(
            request=request,
            name="partials/c0rdin8_results.html",
            context={
                "signals": [],
                "error": str(e)
            }
        )

    if result["status"] != "success":

        return templates.TemplateResponse(
            request=request,
            name="partials/c0rdin8_results.html",
            context={
                "signals": [],
                "error": result["message"]
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="partials/c0rdin8_results.html",
        context={
            "signals": result["data"],
            "feed": result["feed"],
            "error": None
        }
    )

# ---------------------------------------------------------------------------
# CONFIG PLUGIN
# ---------------------------------------------------------------------------

@app.post("/plugin/config/profile/load", response_class=HTMLResponse)
async def config_profile_load(request: Request, profile_name: str = Form(...)):
    host = get_host(request)
    try:
        host.set_active_profile(profile_name)
        profile  = host.get_active_profile()
        new_name = profile.get("dashboard_name", "JagDash")
        from theme_engine import generate_css, normalize_asset_path
        new_css  = generate_css(get_theme(profile))
        raw_logo = profile.get("logo_path", "").strip()
        logo_url = normalize_asset_path(raw_logo) if raw_logo else ""
        oob_title = (f'<h1 class="dashboard-title" id="dashboard-title"'
                     f' hx-swap-oob="true">{new_name}</h1>')
        oob_style = f'<style id="jagdash-theme" hx-swap-oob="true">{new_css}</style>'
        if logo_url:
            oob_logo = (f'<img src="{logo_url}" alt="Logo"'
                        f' class="sidebar-logo" id="sidebar-logo" hx-swap-oob="true">')
        else:
            oob_logo = '<span id="sidebar-logo" hx-swap-oob="true"></span>'
        feedback = f'<div class="success-msg">Profile \'{profile_name}\' loaded.</div>'
        return HTMLResponse(feedback + oob_title + oob_style + oob_logo)
    except Exception as e:
        return error_fragment(f"Failed to load profile: {e}")

@app.post("/plugin/config/profile/create", response_class=HTMLResponse)
async def config_profile_create(request: Request, profile_name: str = Form(...)):
    host = get_host(request)
    if not profile_name.strip():
        return error_fragment("Profile name cannot be empty.")
    try:
        host.create_profile(profile_name.strip())
        return success_fragment(f"Profile '{profile_name}' created.")
    except Exception as e:
        return error_fragment(f"Failed to create profile: {e}")


@app.post("/plugin/config/settings/save", response_class=HTMLResponse)
async def config_settings_save(
    request: Request,
    dashboard_name: str = Form("JagDash"),
    logo_path:      str = Form(""),
):
    host = get_host(request)
    try:
        host.update_profile_value("dashboard_name", dashboard_name)
        host.update_profile_value("logo_path", logo_path)
        oob_title = (f'<h1 class="dashboard-title" id="dashboard-title"'
                     f' hx-swap-oob="true">{dashboard_name}</h1>')
        return HTMLResponse('<div class="success-msg">Settings saved.</div>' + oob_title)
    except Exception as e:
        return error_fragment(f"Failed to save settings: {e}")


@app.post("/plugin/config/apikeys/save", response_class=HTMLResponse)
async def config_apikeys_save(
    request:           Request,
    newsapi_key:       str = Form(""),
    coinmarketcap_key: str = Form(""),
):
    host = get_host(request)
    try:
        saved    = []
        warnings = []

        if newsapi_key.strip():
            host.update_api_key("newsapi", newsapi_key.strip())
            saved.append("NewsAPI")
            # Warn if a key for this service is also in .env
            if os.getenv("NEWSAPI_KEY"):
                warnings.append(
                    "NewsAPI key is also set in .env — "
                    ".env takes priority over profile keys"
                )

        if coinmarketcap_key.strip():
            host.update_api_key("coinmarketcap", coinmarketcap_key.strip())
            saved.append("CoinMarketCap")
            if os.getenv("COINMARKETCAP_KEY"):
                warnings.append(
                    "CoinMarketCap key is also set in .env — "
                    ".env takes priority over profile keys"
                )

        if not saved:
            return success_fragment("No changes made (all fields were blank).")

        msg = f"Saved: {', '.join(saved)}."
        if warnings:
            # Return both a success message and warning messages
            parts = [f'<div class="success-msg">{msg}</div>']
            for w in warnings:
                parts.append(f'<div class="info-msg">⚠ {w}</div>')
            return HTMLResponse("".join(parts))

        return success_fragment(msg)

    except Exception as e:
        return error_fragment(f"Failed to save API keys: {e}")


@app.post("/plugin/config/theme/preset", response_class=HTMLResponse)
async def config_theme_preset(request: Request, preset_name: str = Form(...)):
    """
    Load a preset and return the theme form with those values pre-filled.
    HTMX drops this into #theme-form-area — no page reload needed.
    """
    host    = get_host(request)
    profile = host.get_active_profile()
    # Merge preset over current theme so non-color fields also update
    preset  = get_preset(preset_name)
    return templates.TemplateResponse(
        request=request, name="partials/theme_form.html",
        context={"theme": preset}
    )


@app.post("/plugin/config/theme/save", response_class=HTMLResponse)
async def config_theme_save(
    request: Request,
    preset:             str   = Form("dark"),
    color_bg:           str   = Form(""),
    color_surface:      str   = Form(""),
    color_surface_raised: str = Form(""),
    color_border:       str   = Form(""),
    color_fg:           str   = Form(""),
    color_fg_muted:     str   = Form(""),
    color_accent:       str   = Form(""),
    color_success:      str   = Form(""),
    color_error:        str   = Form(""),
    color_warning:      str   = Form(""),
    font_size_base:     int   = Form(14),
    space_scale:        float = Form(1.0),
    sidebar_width:      int   = Form(220),
    border_radius:      str   = Form("medium"),
    bg_image:           str   = Form(""),
    bg_image_opacity:   float = Form(0.15),
):
    host = get_host(request)
    theme_dict = {
        "preset":               preset,
        "color_bg":             color_bg,
        "color_surface":        color_surface,
        "color_surface_raised": color_surface_raised,
        "color_border":         color_border,
        "color_fg":             color_fg,
        "color_fg_muted":       color_fg_muted,
        "color_accent":         color_accent,
        "color_success":        color_success,
        "color_error":          color_error,
        "color_warning":        color_warning,
        "font_size_base":       font_size_base,
        "space_scale":          round(space_scale, 2),
        "sidebar_width":        sidebar_width,
        "border_radius":        border_radius,
        "bg_image":             bg_image,
        "bg_image_opacity":     round(bg_image_opacity, 2),
    }
    try:
        host.update_profile_value("theme", theme_dict)
        return theme_saved_response("Theme saved.", host.get_active_profile())
    except Exception as e:
        return error_fragment(f"Failed to save theme: {e}")


# ---------------------------------------------------------------------------
# NEWS SCANNER
# ---------------------------------------------------------------------------

@app.post("/plugin/news_scanner/fetch", response_class=HTMLResponse)
async def news_scanner_fetch(
    request: Request,
    watchlist_item: str = Form("Bitcoin"),
    custom_query:   str = Form(""),
):
    query = custom_query.strip() if custom_query.strip() else watchlist_item
    save_plugin_state(request, "news_scanner",
                      {"watchlist_item": watchlist_item, "custom_query": custom_query})
    host    = get_host(request)
    context = PluginContext(host)
    try:
        result = context.request("news.search", {"query": query})
    except Exception as e:
        return templates.TemplateResponse(
            request=request, name="partials/news_scanner_results.html",
            context={"query": query, "articles": [], "error": str(e)}
        )
    articles = result.get("data", []) if result["status"] == "success" else []
    error    = result.get("message") if result["status"] != "success" else None
    return templates.TemplateResponse(
        request=request, name="partials/news_scanner_results.html",
        context={"query": query, "articles": articles, "error": error}
    )


# ---------------------------------------------------------------------------
# NEWS SIGNAL
# ---------------------------------------------------------------------------

@app.post("/plugin/news_signal/fetch", response_class=HTMLResponse)
async def news_signal_fetch(request: Request, query: str = Form("Bitcoin")):
    save_plugin_state(request, "news_signal", {"query": query})
    host    = get_host(request)
    context = PluginContext(host)
    try:
        result = context.request("news.signal", {"query": query})
    except Exception as e:
        return templates.TemplateResponse(
            request=request, name="partials/news_signal_results.html",
            context={"query": query, "error": str(e)}
        )
    if result["status"] != "success":
        return templates.TemplateResponse(
            request=request, name="partials/news_signal_results.html",
            context={"query": query, "error": result.get("message", "Unknown error")}
        )
    data = result["data"]
    return templates.TemplateResponse(
        request=request, name="partials/news_signal_results.html",
        context={
            "query": query, "error": None,
            "signal":        data.get("signal", "NEUTRAL"),
            "bullish_total": data.get("bullish_total", 0),
            "bearish_total": data.get("bearish_total", 0),
            "articles":      data.get("articles", []),
        }
    )


# ---------------------------------------------------------------------------
# STRATEGY ENGINE — routes moved to plugins/strategy_engine/plugin.py
# register_routes() is called automatically at startup.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# OVERVIEW
# ---------------------------------------------------------------------------

@app.post("/plugin/overview/settings", response_class=HTMLResponse)
async def overview_settings_save(
    request:    Request,
    symbol:     str = Form("BTC-USD"),
    news_query: str = Form("Bitcoin"),
    interval:   str = Form("5m"),
    period:     str = Form("1mo"),
):
    host = get_host(request)
    settings = {"symbol": symbol, "news_query": news_query,
                "interval": interval, "period": period}
    try:
        host.update_profile_value("overview", settings)
        save_plugin_state(request, "overview", settings)
        return success_fragment("Overview settings saved.")
    except Exception as e:
        return error_fragment(f"Failed to save: {e}")


@app.post("/plugin/overview/fetch", response_class=HTMLResponse)
async def overview_fetch(
    request:    Request,
    symbol:     str = Form("BTC-USD"),
    news_query: str = Form("Bitcoin"),
    interval:   str = Form("5m"),
    period:     str = Form("1mo"),
):
    host    = get_host(request)
    context = PluginContext(host)
    try:
        result = context.request("overview.summary", {
            "symbol": symbol, "news_query": news_query,
            "interval": interval, "period": period,
        })
    except Exception as e:
        return templates.TemplateResponse(
            request=request, name="partials/overview_results.html",
            context={"error": str(e), "results": {}}
        )
    if result["status"] != "success":
        return templates.TemplateResponse(
            request=request, name="partials/overview_results.html",
            context={"error": result.get("message"), "results": {}}
        )
    data = result["data"]
    return templates.TemplateResponse(
        request=request, name="partials/overview_results.html",
        context={
            "error":      None,
            "symbol":     symbol,
            "news_query": news_query,
            "interval":   interval,
            "period":     period,
            "results":    data.get("results", {}),
        }
    )


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------

@app.get("/api/plugins")
async def api_list_plugins(request: Request):
    host = get_host(request)
    return {"plugins": host.list_plugins(), "capabilities": host.list_capabilities()}


@app.get("/api/market/price")
async def api_market_price(
    request:  Request,
    symbol:   str = "BTC-USD",
    period:   str = "1mo",
    interval: str = "5m",
):
    host    = get_host(request)
    context = PluginContext(host)
    try:
        return context.request("market.price", {
            "symbol": symbol, "period": period,
            "interval": interval, "include_ohlcv": True
        })
    except Exception as e:
        return {"status": "error", "message": str(e)}

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
from starlette.middleware.sessions import SessionMiddleware

from host import PluginHost
from plugin_loader import load_plugins
from plugin_context import PluginContext
from theme_engine import (
    get_style_block, get_theme, get_preset,
    preset_names as get_preset_names, PRESETS
)

load_dotenv()

UI_DEFAULTS = {
    "market_data": {
        "symbol": "BTC-USD", "interval": "5m", "period": "1mo",
    },
    "strategy_engine": {
        "symbol": "BTC-USD", "interval": "5m", "period": "1mo",
    },
    "news_scanner":  {"watchlist_item": "Bitcoin", "custom_query": ""},
    "news_signal":   {"query": "Bitcoin"},
    "overview":      {"symbol": "BTC-USD", "news_query": "Bitcoin",
                      "interval": "5m", "period": "1mo"},
}


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
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_host(request: Request) -> PluginHost:
    return request.app.state.host


def get_plugin_state(request: Request, plugin_name: str) -> dict:
    defaults = UI_DEFAULTS.get(plugin_name, {})
    saved    = request.session.get(f"ui_{plugin_name}", {})
    return {**defaults, **saved}


def save_plugin_state(request: Request, plugin_name: str, values: dict) -> None:
    request.session[f"ui_{plugin_name}"] = values


def base_context(request: Request) -> dict:
    """
    Build the context dict needed by base.html.
    Called by every route that returns a full page (just the index route).
    The theme_css variable is the injected <style> block.
    """
    host    = get_host(request)
    profile = host.get_active_profile()
    return {
        "dashboard_name": profile.get("dashboard_name", "JagDash"),
        "plugins":        host.list_plugins(),
        "theme_css":      get_style_block(profile),
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


# ---------------------------------------------------------------------------
# OOB STYLE REFRESH HELPER
# After saving theme, we return the feedback message plus an OOB swap
# that updates the <style> block in <head>.
# We include a full-page reload trigger instead — simpler and reliable,
# since the theme affects the layout itself (sidebar width, spacing).
# ---------------------------------------------------------------------------

def theme_saved_response(message: str, profile: dict) -> HTMLResponse:
    """
    Return a success message that also triggers a full page reload.
    Unlike the earlier HX-Refresh approach on config saves, theme changes
    genuinely need a full reload because they affect the layout dimensions
    (sidebar width, spacing scale) which the browser has already rendered.
    A partial swap would leave the old layout in place until reload.
    """
    response = HTMLResponse(
        f'<div class="success-msg">{message} Applying…</div>'
    )
    response.headers["HX-Refresh"] = "true"
    return response


# ---------------------------------------------------------------------------
# MARKET DATA
# ---------------------------------------------------------------------------

@app.post("/plugin/market_data/fetch", response_class=HTMLResponse)
async def market_data_fetch(
    request: Request,
    symbol:   str = Form("BTC-USD"),
    period:   str = Form("1mo"),
    interval: str = Form("5m"),
):
    save_plugin_state(request, "market_data",
                      {"symbol": symbol, "period": period, "interval": interval})
    host    = get_host(request)
    context = PluginContext(host)
    try:
        result = context.request("market.price", {
            "symbol": symbol, "period": period,
            "interval": interval, "include_ohlcv": True
        })
    except Exception as e:
        return HTMLResponse(content=f'<div class="error-msg">Request failed: {e}</div>')
    if result["status"] != "success":
        return HTMLResponse(content=f'<div class="error-msg">{result["message"]}</div>')
    records = result["data"]
    return templates.TemplateResponse(
        request=request, name="partials/market_data_results.html",
        context={
            "symbol": symbol, "records": records,
            "meta": result.get("meta", {}),
            "latest_close": records[-1]["close"] if records else None,
            "candle_count": len(records),
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
        profile   = host.get_active_profile()
        new_name  = profile.get("dashboard_name", "JagDash")
        oob_title = (f'<h1 class="dashboard-title" id="dashboard-title"'
                     f' hx-swap-oob="true">{new_name}</h1>')
        response  = HTMLResponse(
            f'<div class="success-msg">Profile \'{profile_name}\' loaded.</div>' + oob_title
        )
        # Reload so theme also updates
        response.headers["HX-Refresh"] = "true"
        return response
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
async def config_apikeys_save(request: Request, newsapi_key: str = Form("")):
    host = get_host(request)
    try:
        if newsapi_key.strip():
            host.update_api_key("newsapi", newsapi_key.strip())
            return success_fragment("API key saved.")
        return success_fragment("No changes made (field was blank).")
    except Exception as e:
        return error_fragment(f"Failed to save API key: {e}")


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
# STRATEGY ENGINE
# ---------------------------------------------------------------------------

@app.post("/plugin/strategy_engine/run", response_class=HTMLResponse)
async def strategy_engine_run(
    request: Request,
    symbol:              str                 = Form("BTC-USD"),
    interval:            str                 = Form("5m"),
    period:              str                 = Form("1mo"),
    selected_strategies: Optional[List[str]] = Form(None),
):
    form_data = await request.form()
    weights   = {}
    for key, value in form_data.multi_items():
        if key.startswith("weight_"):
            name = key[len("weight_"):]
            try:
                weights[name] = float(value)
            except (ValueError, TypeError):
                weights[name] = 1.0

    save_plugin_state(request, "strategy_engine",
                      {"symbol": symbol, "interval": interval, "period": period})

    if not selected_strategies:
        return HTMLResponse(
            '<div class="error-msg">No strategies selected.</div>')

    for name in selected_strategies:
        weights.setdefault(name, 1.0)

    host    = get_host(request)
    context = PluginContext(host)

    try:
        sm             = host.plugins["strategy_engine"]["module"]
        buy_threshold  = sm.BUY_THRESHOLD
        sell_threshold = sm.SELL_THRESHOLD
        signal_scores  = sm.SIGNAL_SCORES
    except (KeyError, AttributeError):
        buy_threshold  = 0.25
        sell_threshold = -0.25
        signal_scores  = {"BUY": 1.0, "SELL": -1.0, "HOLD": 0.0, "WATCH": 0.0}

    try:
        result = context.request("market.strategy.signal", {
            "symbol": symbol, "interval": interval, "period": period,
            "strategies": selected_strategies, "weights": weights,
        })
    except Exception as e:
        return templates.TemplateResponse(
            request=request, name="partials/strategy_engine_results.html",
            context={"error": str(e)}
        )
    if result["status"] != "success":
        return templates.TemplateResponse(
            request=request, name="partials/strategy_engine_results.html",
            context={"error": result.get("message", "Unknown error")}
        )
    data = result["data"]
    return templates.TemplateResponse(
        request=request, name="partials/strategy_engine_results.html",
        context={
            "error": None, "symbol": symbol,
            "combined":        data.get("combined", {}),
            "signals":         data.get("signals", {}),
            "weights":         data.get("weights", {}),
            "strategy_errors": data.get("strategy_errors", {}),
            "market_meta":     data.get("market_meta", {}),
            "signal_scores":   signal_scores,
            "buy_threshold":   buy_threshold,
            "sell_threshold":  sell_threshold,
        }
    )


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

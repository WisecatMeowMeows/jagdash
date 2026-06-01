"""
main.py — JagDash FastAPI entry point
Replaces jagdash.py (Streamlit). Streamlit still works in parallel via jagdash.py.

To run:
    uvicorn main:app --reload --port 8000

The --reload flag makes uvicorn watch for file changes and restart automatically.
This is equivalent to Streamlit's auto-reload behavior during development.
Remove --reload in production.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from host import PluginHost
from plugin_loader import load_plugins
from plugin_context import PluginContext

# ---------------------------------------------------------------------------
# Load environment variables from .env file
# os.getenv() reads from the environment. load_dotenv() populates the
# environment from the .env file first, so os.getenv() finds those values.
# This must happen before anything that reads env vars (like api keys).
# ---------------------------------------------------------------------------
load_dotenv()


# ---------------------------------------------------------------------------
# Application lifespan — startup and shutdown logic
#
# FastAPI uses an "async context manager" for startup/shutdown.
# The code before `yield` runs once when the server starts.
# The code after `yield` runs once when the server stops.
# We store the host on app.state so every request handler can access it
# without using a global variable.
#
# Why not a global? Global variables in async servers can cause subtle bugs
# with concurrency. app.state is the FastAPI-sanctioned place for shared state.
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    host = PluginHost()
    plugins = load_plugins()
    for plugin in plugins:
        host.register_plugin(plugin)

    # Validate that all plugin dependencies are met
    missing = host.validate_dependencies()
    if missing:
        print("WARNING: Unmet plugin dependencies:")
        for m in missing:
            print(f"  {m['plugin']} requires '{m['missing']}' which is not loaded")

    app.state.host = host
    print(f"JagDash started. Loaded plugins: {host.list_plugins()}")

    yield  # Server runs here, handling requests

    # --- Shutdown (nothing needed yet) ---
    print("JagDash shutting down.")


# ---------------------------------------------------------------------------
# FastAPI app instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="JagDash",
    description="Plugin-based dashboard framework",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Static files and templates
#
# StaticFiles mounts a directory so files in it are served directly by the
# web server without going through Python route handlers. Anything in static/
# is available at /static/filename.css, /static/filename.js, etc.
#
# Jinja2Templates tells FastAPI where to find .html template files.
# ---------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Helper: get host from request
# This small function keeps route handlers clean — they call get_host(request)
# instead of reaching into request.app.state.host directly every time.
# ---------------------------------------------------------------------------
def get_host(request: Request) -> PluginHost:
    return request.app.state.host


# ---------------------------------------------------------------------------
# ROUTES
#
# HTTP GET  = browser is asking for something (page load, data fetch)
# HTTP POST = browser is sending something (form submit, button action)
#
# The function name doesn't matter to HTTP — only the decorator path matters.
# But good function names make the code readable.
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Serve the main dashboard page.

    We pass data into the template as keyword arguments after 'request'.
    Jinja2 makes those available as variables inside the HTML template.
    """
    host = get_host(request)
    profile = host.get_active_profile()

    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={
            "dashboard_name": profile.get("dashboard_name", "JagDash"),
            "plugins": host.list_plugins(),
            "active_plugin": None,
        }
    )


@app.get("/plugin/{plugin_name}", response_class=HTMLResponse)
async def load_plugin(request: Request, plugin_name: str):
    """
    Return the UI for a specific plugin as an HTML fragment.

    This is an HTMX target — when the user clicks a plugin in the sidebar,
    HTMX calls this URL and drops the response into the main content area.
    No full page reload. Only the content area updates.

    The {plugin_name} in the path is a "path parameter" — FastAPI extracts it
    from the URL automatically and passes it as the plugin_name argument.
    """
    host = get_host(request)

    if plugin_name not in host.plugins:
        return HTMLResponse(
            content=f'<div class="error-msg">Plugin "{plugin_name}" not found.</div>',
            status_code=404
        )

    plugin_data = host.plugins[plugin_name]
    plugin_module = plugin_data["module"]

    # Each plugin can optionally define get_ui_context(context) returning a dict
    # of template variables. If it doesn't, we use an empty dict.
    context = PluginContext(host)
    ui_context = {}

    if hasattr(plugin_module, "get_ui_context"):
        try:
            ui_context = plugin_module.get_ui_context(context)
        except Exception as e:
            return HTMLResponse(
                content=f'<div class="error-msg">Plugin "{plugin_name}" failed to load: {e}</div>',
                status_code=500
            )

    # Try to render using a plugin-specific partial template first.
    # Fall back to a generic "this plugin has no UI" message.
    template_name = f"partials/{plugin_name}.html"
    try:
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={"plugin_name": plugin_name, **ui_context}
        )
    except Exception:
        return HTMLResponse(
            content=f'<div class="plugin-no-ui"><p>Plugin <strong>{plugin_name}</strong> has no UI panel.</p></div>'
        )


@app.post("/plugin/market_data/fetch", response_class=HTMLResponse)
async def market_data_fetch(
    request: Request,
    symbol: str = Form("BTC-USD"),
    period: str = Form("1y"),
    interval: str = Form("1d"),
):
    """
    Handle the Market Data fetch button.

    Form(...) tells FastAPI to read these values from an HTML form POST body.
    The default values ("BTC-USD", "1y", "1d") are used if the form field
    is missing — same pattern as payload.get("key", default) in the plugins.

    Returns an HTML fragment that HTMX drops into the results area.
    """
    host = get_host(request)
    context = PluginContext(host)

    try:
        result = context.request(
            "market.price",
            {
                "symbol": symbol,
                "period": period,
                "interval": interval,
                "include_ohlcv": True,
            }
        )
    except Exception as e:
        return HTMLResponse(
            content=f'<div class="error-msg">Request failed: {e}</div>'
        )

    if result["status"] != "success":
        return HTMLResponse(
            content=f'<div class="error-msg">{result["message"]}</div>'
        )

    records = result["data"]
    meta = result.get("meta", {})
    latest_close = records[-1]["close"] if records else None

    return templates.TemplateResponse(
        request=request,
        name="partials/market_data_results.html",
        context={
            "symbol": symbol,
            "records": records,
            "meta": meta,
            "latest_close": latest_close,
            "candle_count": len(records),
        }
    )


# ---------------------------------------------------------------------------
# API routes — return JSON, used for JavaScript fetch calls or direct API use
#
# These exist alongside the HTML routes. The same PluginHost serves both.
# A chart library (like Lightweight Charts) will call /api/market/price
# and get JSON back to render the chart — HTML routes can't do that.
# ---------------------------------------------------------------------------

@app.get("/api/plugins")
async def api_list_plugins(request: Request):
    """Return the list of loaded plugins and their manifests as JSON."""
    host = get_host(request)
    return {
        "plugins": host.list_plugins(),
        "manifests": host.get_manifests(),
        "capabilities": host.list_capabilities(),
    }


@app.get("/api/market/price")
async def api_market_price(
    request: Request,
    symbol: str = "BTC-USD",
    period: str = "1y",
    interval: str = "1d",
):
    """
    JSON endpoint for market price data.
    Query parameters: /api/market/price?symbol=ETH-USD&period=3mo&interval=1d

    Query parameters are different from path parameters:
    - Path:  /api/market/{symbol}  — symbol is part of the URL
    - Query: /api/market/price?symbol=BTC  — symbol comes after the ?
    FastAPI handles both automatically based on the function signature.
    """
    host = get_host(request)
    context = PluginContext(host)

    try:
        result = context.request(
            "market.price",
            {"symbol": symbol, "period": period, "interval": interval, "include_ohlcv": True}
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return result

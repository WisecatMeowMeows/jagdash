"""
main.py — JagDash FastAPI entry point

To run:
    uvicorn main:app --reload --port 8000
"""

import os
import sys
from contextlib import asynccontextmanager
import tkinter as tk
from tkinter import filedialog
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from typing import List, Optional
from pathlib import Path
from starlette.middleware.sessions import SessionMiddleware
from jinja2 import ChoiceLoader, FileSystemLoader, TemplateNotFound

from host import PluginHost
from plugin_loader import load_plugins
from plugin_context import PluginContext
from theme_engine import (
    get_theme, generate_css, get_preset,
    preset_names as get_preset_names, PRESETS
)

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

plugin_dir = "plugins" #default directory for plugins. user can select new one in app

# Find where main.py lives to keep global template path absolute and safe
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GLOBAL_TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# Initialize templates with the global folder by default
templates = Jinja2Templates(directory=GLOBAL_TEMPLATE_DIR)

# ---------------------------------------------------------------------------
# Core Plugin Initialization Engine
# ---------------------------------------------------------------------------

def initialize_plugin_host(app_instance: FastAPI, target_dir: str) -> PluginHost:
    """
    Scans a given target directory, initializes a clean PluginHost instance,
    and dynamically binds absolute localized paths for all plugin suites.
    """
    print(f"\n[JagDash] Initializing plugin stack from directory: {target_dir}")
    
    abs_path = os.path.abspath(target_dir)
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)
        
    new_host = PluginHost()
    loaded_modules = load_plugins(target_dir) 
    
    for plugin in loaded_modules:
        new_host.register_plugin(plugin)
        
    # Build absolute file system paths for all plugins
    plugin_loaders = []
    for plugin_name, plugin_data in new_host.plugins.items():
        try:
            plugin_file_path = plugin_data["module"].__file__
            plugin_module_dir = os.path.dirname(os.path.abspath(plugin_file_path))
            
            # Map the plugin folder directly into Jinja2
            plugin_loaders.append(FileSystemLoader(plugin_module_dir))
            print(f"  template path registered: {plugin_module_dir}")
        except Exception as e:
            print(f"  WARNING: Could not parse template path for {plugin_name}: {e}")

    # 3. Fallbacks: Add global roots AND handle 'partials/' path redirections
    global_loader = FileSystemLoader(GLOBAL_TEMPLATE_DIR)
    
    # We combine all plugin directories so Jinja treats them as a unified lookup stack
    from jinja2 import ChoiceLoader, PrefixLoader # Ensure PrefixLoader is imported
    
    # This maps "partials/something.html" directly back to the roots of our plugin directories
    # and the global templates directory as a fallback.
    all_roots = plugin_loaders + [global_loader]
    partials_redirect_loader = PrefixLoader({
        "partials": ChoiceLoader(all_roots)
    })

    # Order of priority: 
    # 1. Look for flat names in plugins/global
    # 2. Look for "partials/name" strings redirected directly to our roots
    combined_loaders = all_roots + [partials_redirect_loader]

    # Apply loaders and strip the stale matching cache memory
    templates.env.loader = ChoiceLoader(combined_loaders)
    templates.env.cache = None  

    # Rebind the loader and wipe Jinja's matching memory cache completely
    templates.env.loader = ChoiceLoader(combined_loaders)
    templates.env.cache = None  # Prevents Jinja from using old folder paths for sub-templates
    
    # Force Jinja to drop its internal parsed template cache mapping
    templates.env.bytecode_cache = None 

    # Dependency Validation
    missing = new_host.validate_dependencies()
    if missing:
        print("WARNING: Unmet plugin dependencies:")
        for m in missing:
            print(f"  {m['plugin']} requires '{m['missing']}' — not loaded")
            
    # Route Registration
    for plugin_name, plugin_data in new_host.plugins.items():
        plugin_module = plugin_data["module"]
        if hasattr(plugin_module, "register_routes"):
            try:
                plugin_module.register_routes(app_instance, templates, lambda req: req.app.state.host)
                print(f"  routes registered: {plugin_name}")
            except Exception as e:
                print(f"  WARNING: {plugin_name}.register_routes() failed/already bound: {e}")
                
    print(f"[JagDash] Initialization complete. Active: {new_host.list_plugins()}\n")
    return new_host




# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.host = initialize_plugin_host(app, plugin_dir)

    from pathlib import Path as _Path
    dotenv_file = _Path(__file__).parent / ".env"
    print(f"  .env file: {'found' if dotenv_file.exists() else 'NOT FOUND — check path'}")
    for _svc, _var in [("newsapi", "NEWSAPI_KEY"), ("coinmarketcap", "COINMARKETCAP_KEY"),
                        ("session", "SESSION_SECRET")]:
        _val = os.getenv(_var, "")
        print(f"  {_var}: {'set (' + str(len(_val)) + ' chars)' if _val else 'NOT SET'}")

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
    host    = get_host(request)
    profile = host.get_active_profile()
    theme   = get_theme(profile)
    from theme_engine import generate_css, normalize_asset_path
    raw_logo = profile.get("logo_path", "").strip()
    
    # Track the name of the root directory configurations cleanly
    global plugin_dir
    abs_path = os.path.abspath(plugin_dir)
    folder_name = os.path.basename(abs_path)
    
    return {
        "dashboard_name":    profile.get("dashboard_name", "JagDash"),
        "plugins":           host.list_plugins(),
        "theme_css_content": generate_css(theme),
        "logo_path":         normalize_asset_path(raw_logo) if raw_logo else "",
        "current_folder_name": folder_name,
        "full_path":         abs_path
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
        # this comment may be defunct: Look for "news_scanner.html" directly in the ChoiceLoader stack
        return templates.TemplateResponse(
            request=request,
            name=f"{plugin_name}.html", 
            context={"plugin_name": plugin_name, "ui": ui_state, **ui_context}
        )
    except Exception as e:
        return HTMLResponse(
            content=f'<div class="error-msg">Failed to render template partial: {e}</div>',
            status_code=500
        )

    
    # -------------------------------------------------------------------------
    # SMART FALLBACK LOOKUP
    # -------------------------------------------------------------------------
    try:
        # 1. First choice: Try to find the standalone file (works for plugin directories)
        return templates.TemplateResponse(
            request=request,
            name=f"{plugin_name}.html", 
            context={"plugin_name": plugin_name, "ui": ui_state, **ui_context}
        )
    except TemplateNotFound:
        try:
            # 2. Second choice: Fall back to your original nested global partial structure
            return templates.TemplateResponse(
                request=request,
                name=f"partials/{plugin_name}.html", 
                context={"plugin_name": plugin_name, "ui": ui_state, **ui_context}
            )
        except Exception as fallback_error:
            return HTMLResponse(
                content=f'<div class="error-msg">Template not found in folder or global partials: {fallback_error}</div>',
                status_code=500
            )
    except Exception as e:
        return HTMLResponse(
            content=f'<div class="error-msg">Failed to render template partial: {e}</div>',
            status_code=500
        )


# ---------------------------------------------------------------------------
# EXTENDED HTMX RUNTIME CONFIGURATION ROUTES
# ---------------------------------------------------------------------------

@app.post("/plugins/select-folder", response_class=HTMLResponse)
async def select_folder(request: Request):
    global plugin_dir
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    root.option_add('*foreground', 'black')
    root.option_add('*background', '#f0f0f0')
    
    chosen_dir = filedialog.askdirectory(title="Select Plugin Directory (Double-click to enter, then click Open)")
    
    # Process fallback tracking configurations
    current_abs_path = os.path.abspath(plugin_dir)
    current_folder_name = os.path.basename(current_abs_path)
    
    if chosen_dir and os.path.isdir(chosen_dir):
        chosen_dir = os.path.abspath(chosen_dir)
        repo_root = os.path.abspath(os.path.dirname(__file__))
        
        if chosen_dir == repo_root or os.path.exists(os.path.join(chosen_dir, "theme_engine.py")):
            from tkinter import messagebox
            messagebox.showerror(
                "Invalid Directory Selection", 
                "You selected the main repository root folder instead of a specific plugin subfolder.\n\n"
                "Please double-click into your desired plugin folder first before clicking 'Open'."
            )
            root.destroy()
            
            active_plugins = request.app.state.host.list_plugins()
            return templates.TemplateResponse(
                request=request,
                name="partials/navbar_fragment.html",
                context={
                    "plugins": active_plugins,
                    "current_folder_name": current_folder_name,
                    "full_path": current_abs_path
                }
            )
            
        root.destroy()
        plugin_dir = chosen_dir
        try:
            request.app.state.host = initialize_plugin_host(request.app, plugin_dir)
            current_abs_path = os.path.abspath(plugin_dir)
            current_folder_name = os.path.basename(current_abs_path)
        except Exception as e:
            print(f"[JagDash Error] Hot reload sequence failed: {e}")
    else:
        root.destroy()
            
    active_plugins = request.app.state.host.list_plugins()
    
    return templates.TemplateResponse(
        request=request,
        name="partials/navbar_fragment.html",
        context={
            "plugins": active_plugins,
            "current_folder_name": current_folder_name,
            "full_path": current_abs_path
        }
    )



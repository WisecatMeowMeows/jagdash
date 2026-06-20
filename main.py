"""
main.py — JagDash FastAPI entry point

To run:
    uvicorn main:app --reload --port 8000
"""

import os
import sys
import json

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
from jinja2 import ChoiceLoader, FileSystemLoader, TemplateNotFound, PrefixLoader

from host import PluginHost
from plugin_loader import load_plugins
from plugin_context import PluginContext
from theme_engine import (
    get_theme, generate_css, get_preset,
    preset_names as get_preset_names, PRESETS
)

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# --- SYSTEM STARTUP RECOVERY (Self-Contained Code Block) ---
plugin_dir = "plugins"  # Default fallback directory layout

try:
    import json
    import os
    profiles_json_file = "jagdash_profiles.json"
    
    if os.path.exists(profiles_json_file):
        with open(profiles_json_file, "r", encoding="utf-8") as f:
            profiles_data = json.load(f)
            
        active_p = profiles_data.get("active_profile", "default")
        saved_dir = profiles_data.get("profiles", {}).get(active_p, {}).get("plugin_suite_dir")
        
        if saved_dir and os.path.isdir(saved_dir):
            plugin_dir = os.path.abspath(saved_dir)
            print(f"[JagDash Boot] Successfully recovered plugin suite folder link: {plugin_dir}")
except Exception as e:
    print(f"[JagDash Boot Warning] Could not recover active plugin suite link: {e}")
# -----------------------------------------------------------


# Find where main.py lives to keep global template path absolute and safe
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GLOBAL_TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# Initialize templates with the global folder by default
templates = Jinja2Templates(directory=GLOBAL_TEMPLATE_DIR)




# ---------------------------------------------------------------------------
# Core Plugin Initialization Engine
# ---------------------------------------------------------------------------

def initialize_plugin_host(app_instance: FastAPI, target_dir: str) -> PluginHost:
    print(f"\n[JagDash] Re-indexing framework runtime stack...")
    
    abs_suite_path = os.path.abspath(target_dir)
    framework_root_plugins = "plugins" 
    
    # ─────────────────────────────────────────────────────────────────────────
    # 1. PARSE SUITE IDENTITY CONFIGURATION FIRST (Branding & Logo Mount)
    # ─────────────────────────────────────────────────────────────────────────
    suite_meta = {"suite_name": "JagDash", "logo_url": ""}
    suite_json_path = os.path.join(abs_suite_path, "suite.json")
    
    if os.path.exists(suite_json_path):
        try:
            with open(suite_json_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            
            suite_meta["suite_name"] = manifest_data.get("suite_name", "JagDash")
            logo_file = manifest_data.get("logo_filename")
            
            # Locate the images subfolder directly inside your external chosen suite
            suite_images_dir = os.path.join(abs_suite_path, "images")
            if os.path.isdir(suite_images_dir):
                # Unmount old framework routes to prevent caching collisions
                app_instance.router.routes = [r for r in app_instance.router.routes if r.path != "/images"]
                
                # Mount the active suite's images subfolder live onto the webserver
                app_instance.mount("/images", StaticFiles(directory=suite_images_dir), name="images")
                print(f"  [Suite Hook Success] Serving active images space from: {suite_images_dir}")
                
                if logo_file:
                    suite_meta["logo_url"] = f"/images/{logo_file}"
                    print(f"  [Suite Hook Success] Bound logo asset target link: {suite_meta['logo_url']}")
        except Exception as e:
            print(f"  [Suite Warning] Failed to parse suite.json parameters: {e}")
    else:
        # Fallback to local root framework assets folder if no suite config is found
        try:
            app_instance.router.routes = [r for r in app_instance.router.routes if r.path != "/images"]
            os.makedirs("images", exist_ok=True)
            app_instance.mount("/images", StaticFiles(directory="images"), name="images")
        except Exception:
            pass

    # Save the verified identities onto the global application memory state
    app_instance.state.suite_meta = suite_meta

    # ─────────────────────────────────────────────────────────────────────────
    # 2. LOAD COMPONENT MODULES (Core Framework + Chosen External Suite)
    # ─────────────────────────────────────────────────────────────────────────
    new_host = PluginHost()
    all_loaded_modules = []

    # Layer A: Scan the root directory (always ensures config_plugin loads)
    if os.path.isdir(framework_root_plugins):
        framework_modules = load_plugins(framework_root_plugins)
        all_loaded_modules.extend(framework_modules)

    # Layer B: Scan the chosen external target directory suite
    if abs_suite_path != os.path.abspath(framework_root_plugins) and os.path.isdir(abs_suite_path):
        if abs_suite_path not in sys.path:
            sys.path.insert(0, abs_suite_path)
        suite_modules = load_plugins(abs_suite_path)
        all_loaded_modules.extend(suite_modules)

    # Register all combined modules into your central running host router
    for plugin in all_loaded_modules:
        new_host.register_plugin(plugin)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. JINJA2 TEMPLATE CHOICE PATH ENGINE RESOLUTION
    # ─────────────────────────────────────────────────────────────────────────
    plugin_loaders = []
    for plugin_name, plugin_data in new_host.plugins.items():
        try:
            plugin_file_path = plugin_data["module"].__file__
            plugin_module_dir = os.path.dirname(os.path.abspath(plugin_file_path))
            plugin_loaders.append(FileSystemLoader(plugin_module_dir))
        except Exception:
            pass

    global_loader = FileSystemLoader(GLOBAL_TEMPLATE_DIR)
    all_roots = plugin_loaders + [global_loader]
    
    # Enable the 'partials/' prefix helper redirector
    partials_redirect_loader = PrefixLoader({"partials": ChoiceLoader(all_roots)})
    combined_loaders = all_roots + [partials_redirect_loader]

    # Apply configuration and completely wipe Jinja's stale lookup match cache memory
    templates.env.loader = ChoiceLoader(combined_loaders)
    templates.env.cache = None  
    templates.env.bytecode_cache = None

    # ─────────────────────────────────────────────────────────────────────────
    # 4. ROUTE REGISTRATION PROCESSING
    # ─────────────────────────────────────────────────────────────────────────
    for plugin_name, plugin_data in new_host.plugins.items():
        plugin_module = plugin_data["module"]
        if hasattr(plugin_module, "register_routes"):
            try:
                plugin_module.register_routes(app_instance, templates, lambda req: req.app.state.host)
                print(f"  routes registered: {plugin_name}")
            except Exception as e:
                print(f"  WARNING: {plugin_name}.register_routes failed: {e}")
                
    print(f"[JagDash] Re-index complete. Active Title: {suite_meta['suite_name']}\n")
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
    from theme_engine import generate_css
    
    # Extract live dynamic suite profiles
    suite_meta = getattr(request.app.state, "suite_meta", {"suite_name": "JagDash", "logo_url": ""})
    
    # Priority: 1. Suite JSON logo URL -> 2. Global framework profile default logo URL
    logo_path = suite_meta.get("logo_url") or profile.get("logo_path", "").strip()
    
    global plugin_dir
    abs_path = os.path.abspath(plugin_dir)
    folder_name = os.path.basename(abs_path)
    
    return {
        "dashboard_name":    suite_meta.get("suite_name", "JagDash"),
        "plugins":           host.list_plugins(),
        "theme_css_content": generate_css(theme),
        "logo_path":         logo_path, # Returns /images/nitetrader_logo.png safely
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
        plugin_dir = os.path.abspath(chosen_dir)
        
        # --- ATOMIC CORES SAVE RUNTIME LOOP ---
        try:
            import json
            profiles_json_file = "jagdash_profiles.json"
            profiles_data = {"active_profile": "default", "profiles": {"default": {}}}
            
            if os.path.exists(profiles_json_file):
                with open(profiles_json_file, "r", encoding="utf-8") as f:
                    profiles_data = json.load(f)
                    
            active_p = profiles_data.get("active_profile", "default")
            if "profiles" not in profiles_data:
                profiles_data["profiles"] = {}
            if active_p not in profiles_data["profiles"]:
                profiles_data["profiles"][active_p] = {}
                
            # Commit the suite path string directly into the active configuration tree
            profiles_data["profiles"][active_p]["plugin_suite_dir"] = plugin_dir
            
            with open(profiles_json_file, "w", encoding="utf-8") as f:
                json.dump(profiles_data, f, indent=2)
            print(f"[JagDash Profile] Committed active suite persistence link: {plugin_dir}")
        except Exception as e:
            print(f"[JagDash Profile Error] Failed to write suite path tracking configurations: {e}")
        # --------------------------------------
        
        try:
            request.app.state.host = initialize_plugin_host(request.app, plugin_dir)
            current_abs_path = os.path.abspath(plugin_dir)
            current_folder_name = os.path.basename(current_abs_path)
        except Exception as e:
            print(f"[JagDash Error] Hot reload sequence failed: {e}")


            
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



AGENTS.md — JagDash AI Context GuideFile Target: System Prompt Injector for AI Engineering SessionsPlatform Version: 2.0 (Folder-Isolated, Dynamic Suite Architecture)Last Updated: 2026-061. ARCHITECTURAL STACK & ENGINEBackend: Python 3.10+, FastAPI, Uvicorn, Jinja2.Frontend: HTMX (Served locally via /static/htmx.min.js), Vanilla CSS Custom Properties.State Management: Starlette SessionMiddleware for client context, jagdash_profiles.json for persistent user configurations.Core Principle: Strictly server-side rendered HTML fragments. Zero client-side JS frameworks, zero external CDN dependencies, and an absolute ban on streamlit inclusions.2. FILE SYSTEM & PLUGIN SUITE STRUCTUREAll plugins are completely self-contained within their own subdirectories. Plugins can be loaded as a variable suite from anywhere on the host filesystem via the runtime folder browser.textAny-Plugin-Suite-Directory/
└── {plugin_name}/
    ├── plugin.py               # Core logic, capabilities, and dynamic routing
    ├── {plugin_name}.html      # Main panel UI layout fragment (No <html>/<body> tags)
    └── {plugin_name}_results.html # Action/POST execution UI result fragment
Use code with caution.Global Layout Fallback: Global framework templates reside inside the root /templates/ directory.Jinja2 Resolution Ordering: Templates are parsed using a unified ChoiceLoader combined with a PrefixLoader. Jinja2 scans Local Plugin Folders First, then drops back to /templates/. The engine explicitly disables caching (templates.env.cache = None) to enforce live path binding transitions during hot-reload operations.3. CO-LOCATED PLUGIN CONTRACT (v2)Every modular plugin entry point lives at {suite_dir}/{plugin_name}/plugin.py. It must implement the following specification:A. manifest() -> dict [REQUIRED]Defines metadata, data broker hooks, and standard form variable default state attributes.pythondef manifest() -> dict:
    return {
        "name": "plugin_name",             # snake_case, matches parent directory name exactly
        "version": "2.0",
        "provides": ["capability.action"], # String tokens handled by handle_request
        "requires": ["another.capability"], # Dependency capabilities called via context.request()
        "ui_defaults": {                   # Default values injected into UI context
            "setting_name": "default_value",
            "theme_mode": "dark"
        }
    }
Use code with caution.B. handle_request(request: dict, context: PluginContext) -> dict [REQUIRED]The serverless inter-plugin business capability router. Must never raise exceptions.pythondef handle_request(request: dict, context) -> dict:
    capability = request.get("capability")
    payload = request.get("payload", {}) # Always fallback to empty dict
    
    if capability == "capability.action":
        try:
            # Core business logic processing goes here
            return {"status": "success", "data": {"result_value": True}}
        except Exception as e:
            return {"status": "error", "message": f"Execution failure: {str(e)}"}
            
    return {"status": "error", "message": f"Unsupported capability: {capability}"}
Use code with caution.C. get_ui_context(context: PluginContext) -> dict [OPTIONAL]Supplies specialized static or capability-sourced template data variables to {plugin_name}.html during initial panel render sequences. Keep lightweight.D. register_routes(app: FastAPI, templates: Jinja2Templates, get_host: Function) [OPTIONAL]Binds the plugin's interactive endpoints directly onto FastAPI during hot-reload execution loops.Strict Implementation Rules for register_routes:Imports: All FastAPI form, routing, and context dependencies must be imported inside the function scope to isolate runtime compilation namespaces.Type Hints: Explicitly type hint request: Request. Never use object as a type hint; it breaks FastAPI parameter parsing and causes 422 Unprocessable Entity crashes.Template Names: Omit directory folder prefixes like partials/ when pointing to templates. Let the engine handle layout lookup resolutions dynamically.pythondef register_routes(app, templates, get_host):
    from fastapi import Request, Form, Response
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext # Always generate context on demand
    
    @app.post("/plugin/plugin_name/action", response_class=HTMLResponse)
    async def plugin_name_action_unique( # Ensure function name is completely unique app-wide
        request: Request,
        user_input: str = Form("default")
    ):
        # Commit input variables into the active session state pipeline
        request.session["ui_plugin_name"] = {"user_input": user_input}
        
        host = get_host(request)
        context = PluginContext(host)
        
        # Safe execution wrapper for internal capability requests
        try:
            res = context.request("another.capability", {"input": user_input})
            if res["status"] != "success":
                return HTMLResponse(f'<div class="error-msg">{res["message"]}</div>')
        except Exception as e:
            return HTMLResponse(f'<div class="error-msg">Broker crash: {str(e)}</div>')
            
        return templates.TemplateResponse(
            request=request,
            name="plugin_name_results.html", # Scanned dynamically within the folder root
            context={"results": res["data"]}
        )
Use code with caution.4. PATH INDEPENDENCE & PATHLIB MANDATEThe OS Working Directory Rule: The active application runtime location (os.getcwd()) stays permanently bound to the framework repository root folder. Plugins cannot assume paths relative to the current working execution shell.Absolute Resolution Guarantee: Any internal lookup loops, directory iteration scans, or configuration reading tasks must declare locations using an absolute Path(__file__).parent.resolve() configuration wrapper to isolate path tracking states.pythonfrom pathlib import Path
# Ensures structural tracking safely maps regardless of hot-reloaded suite changes
INTERNAL_ASSET_DIR = Path(__file__).parent.resolve() / "assets"
Use code with caution.5. HARD REJECTION LAWS FOR AI AGENTSNEVER attempt to inject plugin-specific route signatures directly into the framework main.py file. All operations belong inside the module's localized register_routes.NEVER trigger full-page layout reloads using the HX-Refresh header structure from fragment targets. If side panels or secondary layouts require independent updates, pass targeted hx-swap-oob="true" blocks in the response text payload.NEVER load file streams or loop calculations directly inside data iteration steps without executing explicit fallback validations first (if not path.exists()).
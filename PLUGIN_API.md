PLUGIN_API.md — JagDash Plugin API SpecificationPlatform Contract Version: 2.0 (Folder-Isolated, Hot-Reload Standard)Target Audience: Developers, Core Integrators, and Automated Agents1. CORE PLUGIN ARCHITECTUREJagDash implements a strict hub-and-spoke mediator architecture. Plugins are completely decoupled modules that must never interact directly or share module-level python import expressions.All computation requests, message broadcasts, and system event sequences pass through the central PluginHost engine using data capabilities tokens.2. CO-LOCATED REPOSITORY STRUCTUREEvery plugin must reside in its own self-contained subdirectory inside the active suite. All python code, interface frames, and action result fragments must live together in the same folder.textAny-Plugin-Suite-Directory/
└── {plugin_name}/                  # Unique snake_case directory identifier
    ├── plugin.py                   # REQUIRED: Core lifecycle contract interface hooks
    ├── {plugin_name}.html          # MAIN VIEW: Primary HTML frame injected on GET clicks
    └── {plugin_name}_results.html  # ACTION RESPONSE: Targeted sub-template fragment returned by POST
Use code with caution.Required Module Hooks (plugin.py Matrix):FunctionRequirementExecution Lifecycle & Purposemanifest()REQUIREDDeclares name, identity versions, capability registries, and interface field default values.handle_request(req, ctx)REQUIREDExecutes synchronous business logic triggered by core framework routing or internal capabilities lookups.get_ui_context(ctx)OPTIONALGenerates supplementary static data variables fed to {plugin_name}.html during initial render cycles.register_routes(app, temp, host)OPTIONALInjects dedicated FastAPI HTTP backend form submission routing handlers live at runtime.3. CORE PLATFORM INTERFACE SPECIFICATIONA. manifest() -> dictpythondef manifest() -> dict:
    return {
        "name": "plugin_name",             # Must match parent folder name exactly
        "version": "2.0",                  # Platform specification version target
        "provides": ["system.metric"],     # Capability tokens processed via handle_request()
        "requires": ["service.database"],  # Token blocks this plugin queries via context.request()
        "ui_defaults": {                   # Standard interface dictionary default settings fallback
            "mode": "detailed",
            "max_records": 50
        }
    }
Use code with caution.Note on State Mapping: When a user enters the plugin workspace, ui_defaults are automatically loaded. If the user previously submitted a layout form, their last-used configuration variables instantly overwrite these settings via the session token store (ui), keeping main.py entirely unaware of individual plugin parameter fields.B. handle_request(request: dict, context: PluginContext) -> dictInvoked synchronously by PluginHost whenever an external core component queries a token declared inside your plugin's provides array.Input Contract Format:json{
  "capability": "system.metric",
  "payload": {
    "max_records": 50
  }
}
Use code with caution.Return Output Requirements:python# SUCCESS OUTCOME: Return standard dictionary containing serializable JSON variables
return {"status": "success", "data": {"records": [1, 2, 3]}}

# FAILURE OUTCOME: Catch all internal tracebacks; return human-readable error messages
return {"status": "error", "message": "Database tracking connection dropped."}
Use code with caution.Strict Execution Rejection Laws:NEVER allow internal unhandled exceptions to escape handle_request. Wrap computation steps in standard try/except closures.ALWAYS use payload.get("key", default) syntax. Never assume a payload input parameter exists.C. get_ui_context(context) -> dictRuns on every primary GET /plugin/{name} panel navigation sequence. Generates secondary dictionary options (e.g., custom selector dropdown collections) needed by {plugin_name}.html. The user's active session state is automatically injected into the template as the ui object variable (accessed as {{ ui.max_records }}). Keep this function lightweight.D. register_routes(app, templates, get_host)Dynamically binds interactive HTTP form targets onto the core FastAPI routing table during application startup or runtime hot-reloads.pythondef register_routes(app, templates, get_host):
    # CRITICAL LAW 1: Dependencies MUST be imported inside the function scope
    from fastapi import Request, Form
    from fastapi.responses import HTMLResponse
    from plugin_context import PluginContext
    
    @app.post("/plugin/plugin_name/execute", response_class=HTMLResponse)
    async def plugin_name_action_endpoint( # CRITICAL LAW 2: Function name must be app-wide unique
        request: Request,                  # CRITICAL LAW 3: Hint explicitly to Request, NEVER object
        mode_input: str = Form("detailed")
    ):
        # 1. Capture and commit interface inputs into the session middleware track
        request.session["ui_plugin_name"] = {"mode": mode_input}
        
        # 2. Reconstruct execution context wrappers
        host = get_host(request)
        context = PluginContext(host)
        
        # 3. Request downstream capabilities securely
        try:
            res = context.request("service.database", {"mode": mode_input})
            if res["status"] != "success":
                return HTMLResponse(f'<div class="error-msg">{res["message"]}</div>')
        except Exception as e:
            return HTMLResponse(f'<div class="error-msg">Broker failure: {str(e)}</div>')
            
        # 4. CRITICAL LAW 4: Render absolute filename paths WITHOUT folder path prefixes
        target_template = "plugin_name_results.html"
        try:
            templates.env.loader.load(templates.env, target_template)
        except Exception:
            target_template = "partials/plugin_name_results.html" # Framework legacy compatibility
            
        return templates.TemplateResponse(
            request=request, name=target_template, context={"data": res["data"]}
        )
Use code with caution.4. THE LIVE CONTEXT SERVICE LAYERThe context engine instance is automatically generated and passed directly into handle_request and register_routes logic blocks.context.request(capability: str, payload: dict) -> dictSynchronously queries an external capability. Raises an exception if the platform target configuration is missing or broken.pythontry:
    response = context.request("service.database", {"query": "all"})
    if response["status"] == "success":
        data = response["data"]
except Exception as e:
    logger.error(f"Downstream capability dependency error: {e}")
Use code with caution.context.publish(event: str, payload: dict) -> NoneTriggers an immediate, asynchronous, system-wide event message transmission. This is a fire-and-forget broadcast that returns no acknowledgement payload. Call this function after a core logic operation completes successfully.pythoncontext.publish("plugin_name.state_updated", {"updated_by": "user_form"})
Use code with caution.5. USER INTERFACE RENDERING SCHEMATICSAll plugin frontends use raw server-side rendered HTML fragments managed by HTMX injection mechanisms.Main View Component ({plugin_name}.html Pattern)This component must be an isolated HTML section block. It must never contain top-level structural layout document declarations like <html>, <head>, or <body> wrapper markup.html<div class="plugin-panel">
    <div class="plugin-header">
        <h2>Custom Core Panel</h2>
    </div>

    <!-- Interactive HTMX Data Request Transmission Form -->
    <form hx-post="/plugin/plugin_name/execute"
          hx-target="#plugin-name-workspace"
          hx-swap="innerHTML"
          hx-indicator="#plugin-name-spinner">
          
        <div class="control-group">
            <label>Operation Mode</label>
            <!-- Injects value from active session state automatically -->
            <input type="text" name="mode_input" value="{{ ui.mode }}" class="text-input">
        </div>
        
        <button type="submit" class="btn btn--primary">Execute Data Run</button>
    </form>

    <div id="plugin-name-spinner" class="htmx-indicator loading-inline">Processing Layout...</div>
    <div id="plugin-name-workspace" class="results-area">
        <p class="placeholder-msg">Awaiting execution action triggers.</p>
    </div>
</div>
Use code with caution.6. PLATFORM INTEGRATION ENGINEERING CHECKLISTUse this checklist when writing or validating a modular plugin module for JagDash:The plugin package is isolated inside its own folder named exactly match manifest()["name"].manifest() contains all required standard schema keys: name, version, provides, requires, and ui_defaults.Every capability declared inside the provides string array is directly mapped to a logical switch block inside handle_request().Every dependency declared inside requires is executed safely wrapped within a standard try/except block.handle_request() never leaks raw runtime code failures; it intercepts all errors and returns a clean {"status": "error", "message": "..."} block.register_routes() defines all external routing dependencies (like Form, Request) strictly inside the function scope block.Target route handlers hint request structures explicitly as request: Request, avoiding generic object types.All POST endpoints update input session state variables using the strict string prefix key standard formatting: request.session["ui_{plugin_name}"].Template response file selections are requested via pure filename strings, omitting hardcoded folder string layouts like partials/.Input elements bind active settings data back to fields using value="{{ ui.field_name }}" to ensure persistent user interface recovery states.The codebase is completely free of any direct references to external dashboard execution tools like streamlit.
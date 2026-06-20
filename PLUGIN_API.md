# PLUGIN_API.md — JagDash Plugin API Specification
**Platform Contract Version**: 2.0 (Folder-Isolated, Hot-Reload Standard)  
**Target Audience**: Developers, Core Integrators, and Automated Agents

---

## 1. CORE PLUGIN ARCHITECTURE
JagDash implements a strict hub-and-spoke mediator architecture. Plugins are completely decoupled modules that must never interact directly or share module-level python `import` expressions. 

All computation requests, message broadcasts, and system event sequences pass through the central `PluginHost` engine using data capabilities tokens.

---

## 2. CO-LOCATED SUITE DIRECTORY MATRIX
Every plugin must reside in its own self-contained subdirectory inside the suite. All python code, interface frames, and action result fragments must live together in the same folder.

The root of the suite directory must host a declarative configuration file and an isolated asset repository:

```text
Any-External-Plugin-Suite/
├── suite.json                      # REQUIRED: Declares suite name and branding graphics
├── images/                         # REQUIRED: Serves the suite's private image assets
│   └── custom_logo.png
└── {plugin_name}/                  # Unique snake_case directory identifier
    ├── plugin.py                   # REQUIRED: Core lifecycle contract interface hooks
    ├── {plugin_name}.html          # MAIN VIEW: Primary HTML frame injected on GET clicks
    └── {plugin_name}_results.html  # ACTION RESPONSE: Target sub-template fragment returned by POST
```

### The `suite.json` Manifest Schema:
```json
{
  "suite_name": "NiteTrader Workspace",
  "logo_filename": "custom_logo.png",
  "default_view": "overview"
}
```
*Note on Asset Routing:* When this suite is loaded, the framework automatically intercepts the root `/images` route path, remapping it directly to point to the active suite's `/images/` subfolder. Your HTML templates can render localized suite images using standard source links (e.g., `<img src="/images/custom_logo.png">`).

---

## 3. CORE PLATFORM INTERFACE SPECIFICATION

### A. `manifest() -> dict`
```python
def manifest() -> dict:
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
```

### B. `handle_request(request: dict, context: PluginContext) -> dict`
Invoked synchronously by `PluginHost` whenever an external component queries a token declared inside your plugin's `provides` array.

#### Return Output Requirements:
```python
# SUCCESS OUTCOME: Return standard dictionary containing serializable JSON variables
return {"status": "success", "data": {"records": []}}

# FAILURE OUTCOME: Catch all internal tracebacks; return human-readable error messages
return {"status": "error", "message": "Database tracking connection dropped."}
```

### C. `register_routes(app, templates, get_host)`
Dynamically binds interactive HTTP form targets onto the core FastAPI routing table during application startup or runtime hot-reloads.

```python
def register_routes(app, templates, get_host):
    # CRITICAL LAW 1: Dependencies MUST be imported inside the function scope
    from fastapi import Request, Form
    from fastapi.responses import HTMLResponse
    
    @app.post("/plugin/plugin_name/execute", response_class=HTMLResponse)
    async def plugin_name_action_endpoint( # CRITICAL LAW 2: Function name must be app-wide unique
        request: Request                   # CRITICAL LAW 3: Hint explicitly to Request, NEVER object
    ):
        form_data = await request.form()   # Async parsing protects against formatting conflicts
        mode_input = form_data.get("mode_input", "detailed")
        
        request.session["ui_plugin_name"] = {"mode": mode_input}
        
        # Render absolute filename paths WITHOUT folder path prefixes (no partials/ needed)
        target_template = "plugin_name_results.html"
        try:
            templates.env.loader.load(templates.env, target_template)
        except Exception:
            target_template = "partials/plugin_name_results.html" # Legacy compatibility fallback
            
        return templates.TemplateResponse(
            request=request, name=target_template, context={"data": []}
        )
```

---

## 4. USER INTERFACE RENDERING SCHEMATICS
All plugin frontends use server-side rendered HTML fragments managed by **HTMX** injection mechanisms.

### Main View Component (`{plugin_name}.html` Pattern)
This component must be an isolated HTML section block. It must **never** contain top-level structural layout document declarations like `<html>`, `<head>`, or `<body>` wrapper markup.

```html
<div class="plugin-panel">
    <div class="plugin-header">
        <h2>Custom Core Panel</h2>
    </div>

    <form hx-post="/plugin/plugin_name/execute"
          hx-target="#plugin-name-workspace"
          hx-swap="innerHTML">
          
        <div class="control-group">
            <label>Operation Mode</label>
            <input type="text" name="mode_input" value="{{ ui.mode }}" class="text-input">
        </div>
        
        <button type="submit" class="btn btn--primary">Execute Data Run</button>
    </form>

    <div id="plugin-name-workspace" class="results-area">
        <p class="placeholder-msg">Awaiting execution action triggers.</p>
    </div>
</div>
```
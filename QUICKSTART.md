QUICKSTART.md — 5-Minute Hello World PluginThis guide walks you through creating a minimal working plugin to verify that your layout and the hot-reload engine are working correctly.For detailed interface design rules and checklists, always refer to PLUGIN_API.md [^133].Step 1: Create Your Plugin FolderCreate a new directory inside your active plugin suite folder. The directory name must be unique and written in snake_case:bashmkdir my_hello_world
cd my_hello_world
Use code with caution.Step 2: Create plugin.pyCreate a file named plugin.py inside that folder and drop in this boilerplate code:python# plugin.py
from fastapi import Request, Form
from fastapi.responses import HTMLResponse
from plugin_context import PluginContext

def manifest() -> dict:
    return {
        "name": "my_hello_world",        # Must match the parent folder name exactly
        "version": "2.0",
        "provides": ["hello.message"],   # Capability token string
        "requires": [],                  # Core capability dependencies
        "ui_defaults": {
            "user_name": "Developer"     # Form input default fallback state
        }
    }

def handle_request(request: dict, context) -> dict:
    capability = request.get("capability")
    payload = request.get("payload", {})
    
    if capability == "hello.message":
        name = payload.get("user_name", "Developer")
        return {"status": "success", "data": f"Hello, {name}! Your platform workspace is live."}
        
    return {"status": "error", "message": f"Unsupported capability: {capability}"}

def register_routes(app, templates, get_host):
    @app.post("/plugin/my_hello_world/greet", response_class=HTMLResponse)
    async def hello_world_greet_endpoint(request: Request, user_name: str = Form("Developer")):
        # 1. Store form variables inside the active session
        request.session["ui_my_hello_world"] = {"user_name": user_name}
        
        # 2. Rebuild context and route request back to handle_request
        host = get_host(request)
        context = PluginContext(host)
        result = handle_request({"capability": "hello.message", "payload": {"user_name": user_name}}, context)
        
        # 3. Render the localized action response fragment template
        return templates.TemplateResponse(
            request=request,
            name="my_hello_world_results.html",
            context={"message": result.get("data"), "error": result.get("message") if result.get("status") == "error" else None}
        )
Use code with caution.Step 3: Create the UI Layout Frame (my_hello_world.html)Create your primary panel template file inside the same folder. This component renders your input form. Do not include <html> or <body> tags:html<!-- my_hello_world.html -->
<div class="plugin-panel">
    <div class="plugin-header">
        <h2>Hello World Workspace</h2>
        <p class="plugin-subtitle">Verify contract v2 lifecycle hot-reloads</p>
    </div>

    <!-- HTMX Interactive Post Target Form Hook -->
    <form hx-post="/plugin/my_hello_world/greet"
          hx-target="#hello-world-results-pane"
          hx-swap="innerHTML">
        
        <div class="control-group">
            <label>Your Name</label>
            <!-- Injects variable value from session track state automatically -->
            <input type="text" name="user_name" value="{{ ui.user_name }}" class="text-input">
        </div>
        
        <button type="submit" class="btn btn--primary">Trigger Greet Capability</button>
    </form>

    <div id="hello-world-results-pane" class="results-area" style="margin-top: 15px;">
        <p class="placeholder-msg">Click trigger button above to fire actions.</p>
    </div>
</div>
Use code with caution.Step 4: Create the Action Fragment (my_hello_world_results.html)Create your secondary target template file inside the same folder. This handles the content swapped into your workspace panel after execution:html<!-- my_hello_world_results.html -->
{% if error %}
    <div class="error-msg">Failed: {{ error }}</div>
{% else %}
    <div class="success-msg" style="padding: 12px; border-left: 4px solid var(--color-success, green);">
        {{ message }}
    </div>
{% endif %}
Use code with caution.Step 5: Test the Hot-Reload LifecycleOpen your browser dashboard panel page workspace.Click 📁 Choose Plugin Folder inside your navbar layout.Use the browser native modal window dialogue to select your plugin suite parent directory.Your new my_hello_world button will appear instantly in the sidebar navigation column. Click it, type a name, and press run to verify execution!
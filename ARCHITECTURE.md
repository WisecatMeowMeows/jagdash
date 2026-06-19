ARCHITECTURE.md — JagDash System ArchitectureFramework Version: 2.0 (Dynamic Suite Hot-Reload Specification)Audience: Human Architects, Maintainers, and Platform Engineers [1]1. CORE SYSTEM DESIGN & PRINCIPLESJagDash is a lightweight, plugin-based dashboard orchestration platform built on FastAPI, HTMX, and Jinja2. The core repository provides foundational application plumbing — routing lifecycles, global session state middleware, profile storage, a unified message bus, and runtime user access authentication.The framework core is intentionally minimalist. It exposes no specific business components on its own. Instead, it serves as an infrastructure engine that discovers, binds, and executes entirely independent plugin extensions on demand.       ┌──────────────────────────────┐
       │     Browser (HTMX View)      │
       └──────────────┬───────────────┘
                      │ HTTP POST / GET
                      ▼
       ┌──────────────────────────────┐
       │       FastAPI Core           │
       │ (Lifespan Core, Middleware)  │
       └──────────────┬───────────────┘
                      │ Routing Dispatch
                      ▼
  ┌───────────────────────────────────────┐
  │         PluginHost (The Hub)          │
  └───────────────────┬───────────────────┘
     ┌────────────────┼────────────────┐
     ▼                ▼                ▼
┌──────────┐     ┌──────────┐     ┌──────────┐
│ Plugin A │     ┌ Plugin B │     │ Plugin C │
│ (Folder) │     │ (Folder) │     │ (Folder) │
└──────────┘     └──────────┘     └──────────┘
Architectural Mandates:The Hub-and-Spoke Pattern: Plugins never establish direct code dependencies or import chains with each other. All inter-plugin operations route securely through the central PluginHost data broker.Decoupled Immutability: Plugins are entirely swappable. A component providing a capability can be swapped out for a different version instantly without impacting downstream consumers.Server-Side Dominance: Content is rendered entirely as targeted HTML fragments on the server before being sent to the client browser. No complex client-side state engines, single-page-app (SPA) frameworks, or build steps are used.2. INTER-PLUGIN COMMUNICATION PIPELINESA. Synchronous Data Broker (Request / Response)When a plugin requires capability data owned by another module, it passes a structural request package through the active runtime context block. PluginHost performs a registry lookup and executes the targeted provider’s underlying logic synchronously.[Plugin A] ─── context.request("capability.token", payload) ───► [PluginHost]
                                                                        │
[Plugin A] ◄─── JSON Context Data Dictionary Return ──────────── [Plugin B]
Use this configuration channel whenever immediate data resolution is necessary before downstream rendering blocks can proceed.B. Asynchronous Message Pipeline (Publish / Subscribe)Plugins can trigger system-wide broadcast tokens across the event bus without expecting a return payload. Any application module explicitly registered to listen for that structural event signature handles the incoming message asynchronously.[Plugin A] ─── context.publish("event.state_changed", data) ───► [PluginHost]
                                                                        │
                                                    ┌───────────────────┴───────────────────┐
                                                    ▼                                       ▼
                                           [Subscribed Plugin]                     [Subscribed Plugin]
Use this configuration channel to signal system updates across independent modules without creating explicit dependencies.3. ENGINE RUNTIME LIFECYCLE & HOT-RELOADPhase I: Initial Application BootstrappingWhen the framework process kicks off via Uvicorn, the lifespan manager initializes. It processes standard relative paths ("plugins") by parsing active modules into memory, resolving core capability registries, validating package dependencies, and compiling baseline routes.Phase II: Runtime Dynamic Suite SwitchingWhen a user triggers the local filesystem folder browser button inside the web UI, a native modal dialogue intercepts the file environment:Safety Interception Check: The backend performs directory validation, rejecting repository root selection errors to prevent operational layout crashes.Sys-Path Registration: The chosen target suite directory path converts to a clean absolute reference layout string and is injected into sys.path.Host Object Recreation: The existing PluginHost mapping instance is safely torn down, a new one compiles from scratch, and active sub-routes bind on the fly.Jinja2 Cache Flushing: To prevent stale template lookup errors, the compilation state caches are cleared (templates.env.cache = None), forcing Jinja to recompile the active template paths in real-time.4. CO-LOCATED REPOSITORY MATRIXJagDash isolates core platform configurations from modular plugin packages. All plugin code assets, master layouts, and individual fragment templates must live together inside self-contained folders.textjagdash/                            # Framework Core Repository
├── main.py                         # FastAPI App Configuration, Lifespan Loops, Core HTTP Routes
├── host.py                         # PluginHost Registry State Management Hub
├── plugin_loader.py                # File Scanner and Dynamic Python Module Compiler
├── plugin_context.py               # Context Engine Wrapper for Inter-Plugin Token Queries
├── theme_engine.py                 # Profile Dictionary Translator to Injected CSS :root Variables
├── config_manager.py               # Reads/Writes Persistent Profile json Records Safely
├── auth.py                         # Single-Password Bcrypt Session Token Context Helpers
├── static/
│   ├── jagdash.css                 # Master Application CSS Framework Blueprint Layouts
│   └── htmx.min.js                 # Local HTMX Core Source Engine (No External CDNs Allowed)
├── templates/
│   ├── base.html                   # Global View Frame Shell Structure (Sidebar, Indicator Rails)
│   └── login.html                  # Isolated Single-View User Access Challenge Layout
│
└── [Any-Plugin-Suite-Directory]/   # Fully Detached, Movable Plugin Suite Folder
    └── {plugin_name}/              # Isolated Component Workspace
        ├── plugin.py               # Manifest Definitions, Request Handlers, and Local Route Mappings
        ├── {plugin_name}.html      # Main View Interface Panel Component Partial Fragment
        ├── {plugin_name}_results.html # Action/Form Post Sub-Template Target Panel View
        └── [assets]/               # Optional Module-Specific Sub-Directories or Strategies
Use code with caution.5. RE-BALANCED JINJA2 LOADER PRIORITY MatrixTo accommodate completely detached, multi-directory plugin packages without duplicating template tracking logic inside main.py, JagDash maps template search environments using an ordered hierarchy:Local Suite File System Loader (Highest Priority): Jinja2 checks the currently selected active plugin directories first to resolve raw filenames (e.g., {plugin_name}.html).Framework Global File System Loader: Looks inside /templates/ for base architectural components (base.html, login.html).Dynamic Prefix Redirect Interceptor: Catches old "partials/{filename}" path declarations automatically, stripping the legacy folder prefix string and routing lookups back to the active local plugin directories.6. SYSTEM PROFILE & CONFIGURATION MECHANICSA. Profiles JSON (jagdash_profiles.json)The dashboard reads tracking attributes from a central config record structure:json{
  "active_profile": "default",
  "profiles": {
    "default": {
      "dashboard_name": "My Dashboard",
      "logo_path": "images/logo.png",
      "theme": {
        "preset": "dark",
        "color_bg": "#121212"
      },
      "plugins": {
        "plugin_name": {"enabled": true}
      },
      "api_keys": {}
    }
  }
}
Use code with caution.B. Theme EngineInstead of maintaining static design files, theme_engine.py processes raw style parameters into a dedicated live variable layout payload:Parses structural profile key mappings during execution loops.Formulates custom style property configurations targeting :root.Injects values dynamically inside a raw <style id="jagdash-theme"> block embedded within base.html.
# ARCHITECTURE.md — JagDash System Architecture
**Framework Version**: 2.0 (Dynamic Suite Hot-Reload Specification)  
**Audience**: Human Architects, Maintainers, and Platform Engineers

---

## 1. CORE SYSTEM DESIGN & PRINCIPLES
JagDash is a lightweight, plugin-based dashboard orchestration platform built on **FastAPI**, **HTMX**, and **Jinja2**. The core repository provides foundational application plumbing — routing lifecycles, global session state middleware, profile storage, a unified message bus, and runtime user access authentication.

The framework core is intentionally minimalist. It exposes no domain-specific business features on its own. Instead, it serves as an infrastructure engine that discovers, binds, and executes independent plugin extensions using a layered scanning hierarchy.

Use code with caution.┌──────────────────────────────┐│     Browser (HTMX View)      │└──────────────┬───────────────┘│ HTTP POST / GET▼┌──────────────────────────────┐│       FastAPI Core           ││ (Lifespan Core, Middleware)  │└──────────────┬───────────────┘│ Routing Dispatch▼┌───────────────────────────────────────┐│         PluginHost (The Hub)          │└───────────────────┬───────────────────┘┌────────────────┴────────────────┐▼                                 ▼┌─────────────────────────┐       ┌─────────────────────────┐│ Framework Root Plugins  │       │  External Chosen Suite  ││ (e.g., config_plugin)   │       │  (e.g., market_data)    │└─────────────────────────┘       └─────────────────────────┘
### Architectural Mandates:
*   **The Hub-and-Spoke Pattern**: Plugins never establish direct code dependencies or import chains with each other. All inter-plugin operations route securely through the central `PluginHost` data broker.
*   **Layered Scanning Isolation**: The engine separates core system infrastructure components from external feature bundles. The framework root `plugins/` folder is hardcoded to index first, ensuring platform tools (like `config_plugin`) remain permanently operational regardless of which external directory workspace is loaded.
*   **Server-Side Dominance**: Content is rendered entirely as targeted HTML fragments on the server before being sent to the client browser. No complex client-side state engines, single-page-app (SPA) frameworks, or build steps are used.

---

## 2. INTER-PLUGIN COMMUNICATION PIPELINES

### A. Synchronous Data Broker (Request / Response)
When a plugin requires data capability owned by another module, it passes a structural request package through the active runtime context block. `PluginHost` performs a registry lookup and executes the targeted provider’s underlying logic synchronously.
[Plugin A] ─── context.request("capability.token", payload) ───► [PluginHost]│[Plugin A] ◄─── JSON Context Data Dictionary Return ──────────── [Plugin B]
### B. Asynchronous Message Pipeline (Publish / Subscribe)
Plugins can trigger system-wide broadcast tokens across the event bus without expecting a return payload. Any application module explicitly registered to listen for that structural event signature handles the incoming message waves asynchronously.
[Plugin A] ─── context.publish("event.state_changed", data) ───► [PluginHost]│[Subscribed Plugins]
---

## 3. ENGINE RUNTIME LIFECYCLE & HOT-RELOAD

### Phase I: Initial Application Bootstrapping
When the framework process kicks off via Uvicorn, the `lifespan` manager initializes. It attempts to recover the last-used workspace suite path directly from the active profile block inside `jagdash_profiles.json`. If no path is found, it falls back cleanly to the local directory layout state.

### Phase II: Runtime Dynamic Suite Switching
When a user triggers the local filesystem folder browser button inside the web UI, a native modal dialogue intercepts the file environment:
1.  **Safety Interception Check**: The backend performs directory validation, rejecting repository root selection errors to prevent operational layout crashes.
2.  **Branding Config Parsing**: The engine opens the suite's private `suite.json` manifest, parsing custom workspace titles and configuration bindings.
3.  **Dynamic Asset Mounting**: FastAPI's internal `/images` directory route is unmounted and instantly remapped to point directly to the newly chosen suite's private `/images/` subfolder, isolating branding graphics.
4.  **Layered Re-Indexing**: The core repository's internal `plugins/` directory is indexed first, followed by the newly targeted external suite folder. Stale modules are purged from memory, and sub-routes are mounted live on the fly.
5.  **Jinja2 Cache Flushing**: To prevent stale template lookup errors, the compilation state caches are cleared (`templates.env.cache = None`), forcing Jinja to recompile the active template paths in real-time.

---

## 4. CO-LOCATED REPOSITORY MATRIX
JagDash isolates core platform configurations from modular plugin packages. All plugin code assets, master layouts, and individual fragment templates must live together inside self-contained folders.

```text
jagdash/                            # Framework Core Repository
├── main.py                         # FastAPI App Configuration, Lifespan Loops, Core HTTP Routes
├── host.py                         # PluginHost Registry State Management Hub
├── plugin_loader.py                # File Scanner and Dynamic Python Module Compiler
├── static/
│   ├── jagdash.css                 # Master Application CSS Framework Blueprint Layouts
│   └── htmx.min.js                 # Local HTMX Core Source Engine (No External CDNs Allowed)
├── templates/
│   ├── base.html                   # Global View Frame Shell Structure (Sidebar, Indicator Rails)
│   └── login.html                  # Isolated Single-View User Access Challenge Layout
├── plugins/                        # System Infrastructure Plugins Folder
│   └── config_plugin/              # Permanent platform profile management utility
│
└── [Any-Plugin-Suite-Directory]/   # Fully Detached, Movable External Plugin Suite Folder
    ├── suite.json                  # REQUIRED: Declarative suite identity config file
    ├── images/                     # REQUIRED: Suite-specific branding assets (e.g., logos)
    └── {plugin_name}/              # Isolated Component Workspace
        ├── plugin.py               # Manifest Definitions, Request Handlers, and Local Route Mappings
        ├── {plugin_name}.html      # Main View Interface Panel Component Partial Fragment
        └── {plugin_name}_results.html # Action/Form Post Sub-Template Target Panel View
```

---

## 5. RE-BALANCED JINJA2 LOADER PRIORITY MATRIX
To accommodate completely detached, multi-directory plugin packages without duplicating template tracking logic inside `main.py`, JagDash maps template search environments using an ordered hierarchy:

1.  **Local Suite File System Loader** (Highest Priority): Jinja2 checks the currently selected active plugin directories first to resolve raw filenames (e.g., `{plugin_name}.html`).
2.  **Framework Global File System Loader**: Looks inside `/templates/` for base architectural components (`base.html`, `login.html`).
3.  **Dynamic Prefix Redirect Interceptor**: Catches legacy `"partials/{filename}"` path declarations automatically, stripping the folder prefix string and routing lookups back to the active local plugin directories.
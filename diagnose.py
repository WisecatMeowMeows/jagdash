"""
diagnose.py — run this to find the real startup/request error

Usage:
    python diagnose.py

This simulates what main.py does at startup and on the first request,
with full tracebacks instead of uvicorn's suppressed 500 error.
"""

import sys
import traceback

print("=" * 60)
print("Step 1: imports")
print("=" * 60)

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("  OK  dotenv")
except Exception as e:
    print(f"  ERR dotenv: {e}")
    sys.exit(1)

try:
    from theme_engine import get_style_block, get_theme, preset_names, get_preset
    print("  OK  theme_engine")
except Exception as e:
    print(f"  ERR theme_engine: {e}")
    traceback.print_exc()

try:
    from host import PluginHost
    print("  OK  host")
except Exception as e:
    print(f"  ERR host: {e}")
    traceback.print_exc()

try:
    from plugin_loader import load_plugins
    print("  OK  plugin_loader")
except Exception as e:
    print(f"  ERR plugin_loader: {e}")
    traceback.print_exc()

try:
    from plugin_context import PluginContext
    print("  OK  plugin_context")
except Exception as e:
    print(f"  ERR plugin_context: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("Step 2: load plugins")
print("=" * 60)

try:
    host = PluginHost()
    plugins = load_plugins()
    for plugin in plugins:
        try:
            host.register_plugin(plugin)
            print(f"  OK  registered: {plugin.manifest()['name']}")
        except Exception as e:
            print(f"  ERR registering plugin: {e}")
            traceback.print_exc()
except Exception as e:
    print(f"  ERR plugin loading: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("Step 3: validate dependencies")
print("=" * 60)

try:
    missing = host.validate_dependencies()
    if missing:
        for m in missing:
            print(f"  MISSING: {m['plugin']} requires '{m['missing']}'")
    else:
        print("  OK  all dependencies met")
except Exception as e:
    print(f"  ERR validate: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("Step 4: simulate index route (get_style_block)")
print("=" * 60)

try:
    profile = host.get_active_profile()
    print(f"  profile keys: {list(profile.keys())}")

    css = get_style_block(profile)
    print(f"  OK  get_style_block, length={len(css)}")
except Exception as e:
    print(f"  ERR get_style_block: {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("Step 5: simulate plugin load_plugin route for each plugin")
print("=" * 60)

context = PluginContext(host)
for plugin_name in host.list_plugins():
    plugin_module = host.plugins[plugin_name]["module"]
    if hasattr(plugin_module, "get_ui_context"):
        try:
            ui_context = plugin_module.get_ui_context(context)
            print(f"  OK  {plugin_name}.get_ui_context -> keys: {list(ui_context.keys())}")
        except Exception as e:
            print(f"  ERR {plugin_name}.get_ui_context: {e}")
            traceback.print_exc()
    else:
        print(f"  --  {plugin_name}: no get_ui_context")

print()
print("Done. If no ERR lines above, the issue is in a template.")
print("In that case, look at the uvicorn terminal output more carefully —")
print("try running: uvicorn main:app --reload --port 8000 2>&1 | tee uvicorn.log")
print("then check uvicorn.log for the full traceback after triggering the error.")
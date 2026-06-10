"""
debug_keys.py — run this to trace the exact key lookup chain.
Run from the repo root with venv active:
    python debug_keys.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv

print("=" * 60)
print("Step 1: load_dotenv")
print("=" * 60)
dotenv_path = Path(__file__).parent / ".env"
result = load_dotenv(dotenv_path=dotenv_path)
print(f"  .env path:   {dotenv_path.resolve()}")
print(f"  .env exists: {dotenv_path.exists()}")
print(f"  load result: {result}  (True=loaded, False=not found)")
print()
print("  Environment after load_dotenv:")
for var in ["NEWSAPI_KEY", "COINMARKETCAP_KEY", "SESSION_SECRET"]:
    val = os.getenv(var, "")
    print(f"    {var}: {'set (' + str(len(val)) + ' chars) = ' + repr(val[:6]) + '...' if val else 'NOT SET'}")

print()
print("=" * 60)
print("Step 2: ConfigManager.get_api_key()")
print("=" * 60)
from config_manager import ConfigManager
cm = ConfigManager()
profile = cm.get_active_profile()
print(f"  Active profile: {cm.get_active_profile_name()}")
print(f"  Profile api_keys: {profile.get('api_keys', {})}")
print()
for svc in ["newsapi", "coinmarketcap"]:
    env_var = f"{svc.upper()}_KEY"
    env_val = os.getenv(env_var, "")
    profile_val = profile.get("api_keys", {}).get(svc, "")
    result = cm.get_api_key(svc)
    print(f"  get_api_key('{svc}'):")
    print(f"    env var {env_var}:  {repr(env_val[:6]) + '...' if env_val else 'NOT SET'}")
    print(f"    profile value:         {repr(profile_val[:6]) + '...' if profile_val else 'NOT SET'}")
    print(f"    → returns:             {repr(result[:6]) + '...' if result else 'EMPTY STRING'}")
    print()

print("=" * 60)
print("Step 3: PluginContext.get_api_key()")
print("=" * 60)
from host import PluginHost
from plugin_loader import load_plugins
from plugin_context import PluginContext

host = PluginHost()
plugins = load_plugins()
for p in plugins:
    host.register_plugin(p)

ctx = PluginContext(host)
for svc in ["newsapi", "coinmarketcap"]:
    result = ctx.get_api_key(svc)
    print(f"  ctx.get_api_key('{svc}'): {repr(result[:6]) + '...' if result else 'EMPTY STRING'}")

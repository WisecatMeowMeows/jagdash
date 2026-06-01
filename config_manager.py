"""
config_manager.py — JagDash profile and configuration manager

Manages jagdash_profiles.json.
API keys: stored in the profile for user-set values,
          with fallback to environment variables loaded from .env.

Why this two-tier approach?
  - .env is for developer/deployment secrets (set once, not user-editable in UI)
  - Profile api_keys is for user-entered keys (editable in the config plugin UI)
  - get_api_key() checks profile first, then env var, so either source works.
    This means you can set NEWSAPI_KEY in .env and it works without any UI config.
"""

import json
import os

CONFIG_FILE = "jagdash_profiles.json"


class ConfigManager:
    def __init__(self):
        self.data = self.load()

    def load(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)

        return {
            "active_profile": "default",
            "profiles": {
                "default": {
                    "dashboard_name": "JagDash",
                    "logo_path": "",
                    "theme": "default",
                    "plugins": {},
                    "api_keys": {}
                }
            }
        }

    def save(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.data, f, indent=4)

    def get_active_profile_name(self):
        return self.data["active_profile"]

    def get_active_profile(self):
        active = self.get_active_profile_name()
        return self.data["profiles"][active]

    def set_active_profile(self, profile_name):
        if profile_name in self.data["profiles"]:
            self.data["active_profile"] = profile_name
            self.save()

    def create_profile(self, profile_name):
        if profile_name not in self.data["profiles"]:
            self.data["profiles"][profile_name] = {
                "dashboard_name": profile_name,
                "logo_path": "",
                "theme": "default",
                "plugins": {},
                "api_keys": {}
            }
            self.save()

    def get_all_profiles(self):
        return list(self.data["profiles"].keys())

    def update_profile_value(self, key, value):
        profile = self.get_active_profile()
        profile[key] = value
        self.save()

    def update_plugin_state(self, plugin_name, enabled):
        profile = self.get_active_profile()
        if "plugins" not in profile:
            profile["plugins"] = {}
        if plugin_name not in profile["plugins"]:
            profile["plugins"][plugin_name] = {}
        profile["plugins"][plugin_name]["enabled"] = enabled
        self.save()

    def get_api_key(self, service_name):
        """
        Get an API key by service name.

        Lookup order:
          1. Active profile's api_keys dict (user-entered via config UI)
          2. Environment variable named <SERVICE_NAME>_KEY in uppercase
             e.g. service_name="newsapi" -> env var "NEWSAPI_KEY"

        This means keys set in .env work automatically without any UI config,
        and keys entered via the config plugin UI take precedence over .env.

        Returns empty string if not found anywhere, matching original behavior.
        """
        # Check profile first
        profile = self.get_active_profile()
        profile_key = profile.get("api_keys", {}).get(service_name, "")
        if profile_key:
            return profile_key

        # Fall back to environment variable
        # Convention: service "newsapi" -> env var "NEWSAPI_KEY"
        env_var_name = f"{service_name.upper()}_KEY"
        env_key = os.getenv(env_var_name, "")
        if env_key:
            return env_key

        return ""

    def update_api_key(self, service_name, value):
        profile = self.get_active_profile()
        if "api_keys" not in profile:
            profile["api_keys"] = {}
        profile["api_keys"][service_name] = value
        self.save()

    # kept for backward compatibility - host.py calls this
    def get(self):
        return self.data

    def update(self, key, value):
        self.data[key] = value
        self.save()

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
                    "api_keys": {
                        "newsapi": ""
                    }
                }
            }
        }

    def save(self):
        with open(CONFIG_FILE, "w") as f:
            json.dump(
                self.data,
                f,
                indent=4
            )

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
                "theme": "default",
                "plugins": {},
                "api_keys": {
                    "newsapi": ""
                }
            }
            self.save()

    def get_all_profiles(self):
        return list(
            self.data["profiles"].keys()
        )

    def update_profile_value(
        self,
        key,
        value
    ):
        profile = self.get_active_profile()
        profile[key] = value
        self.save()

    def update_plugin_state(
        self,
        plugin_name,
        enabled
    ):
        profile = self.get_active_profile()

        if "plugins" not in profile:
            profile["plugins"] = {}

        if plugin_name not in profile["plugins"]:
            profile["plugins"][plugin_name] = {}

        profile["plugins"][plugin_name]["enabled"] = enabled
        self.save()
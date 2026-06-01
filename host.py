from request_schema import RequestSchema
from plugin_context import PluginContext
from event_bus import EventBus
import datetime
from config_manager import ConfigManager

class PluginHost:
    def __init__(self):
        self.plugins = {}
        self.capabilities = {}
        self.logs = []
        self.event_bus = EventBus()
        self.config_manager = ConfigManager()


    def register_plugin(self, plugin_module):
        manifest = plugin_module.manifest()
        plugin_name = manifest["name"]

        self.plugins[plugin_name] = {
            "module": plugin_module,
            "manifest": manifest
        }

        for capability in manifest["provides"]:
            self.capabilities[capability] = plugin_module

        # Auto-register subscriptions
        for event in manifest.get("subscribes", []):
            self.event_bus.subscribe(
                event,
                plugin_name
            )

    def publish_event(self, event_name, payload, metadata=None):
        if metadata is None:
            metadata = {
                "source_plugin": "unknown"
            }

        event = {
            "type": "event",
            "version": "1.0",
            "event_name": event_name,
            "payload": payload,
            "metadata": metadata
        }

        subscribers = self.event_bus.publish(
            event_name,
            event
        )

        results = []

        for plugin_name in subscribers:
            plugin_module = self.plugins[plugin_name]["module"]

        if hasattr(plugin_module, "handle_event"):
            context = PluginContext(self)

            result = plugin_module.handle_event(
                event,
                context
            )

            results.append({
                "plugin": plugin_name,
                "result": result
            })

        return results

    def subscribe_event(self, event_name, plugin_name):
        """event = {
            "type": "event",
            "version": "1.0",
            "event_name": event_name,
            "payload": payload,
            "metadata": {
                "source_plugin": "unknown"
            }
        } """
        self.event_bus.subscribe(
            event_name,
            plugin_name
        )

    def request(self, capability, payload, metadata=None):
        if metadata is None:
            metadata = {
                "source_plugin": "unknown"
            }

        request = {
            "type": "request",
            "version": "1.0",
            "capability": capability,
            "payload": payload,
            "metadata": metadata
        }

        RequestSchema.validate(request)

        plugin = self.capabilities[capability]

        self.logs.append({
            "timestamp": str(datetime.datetime.now()),
            "capability": capability,
            "payload": payload,
            "metadata": metadata
        })

        context = PluginContext(self)

        return plugin.handle_request(
            request,
            context
        )

    def get_event_log(self):
        return self.event_bus.get_event_log()

    def get_subscribers(self):
        return self.event_bus.get_subscribers()

    def list_plugins(self):
        return list(self.plugins.keys())

    def list_capabilities(self):
        return list(self.capabilities.keys())

    def get_manifests(self):
        return {
            name: data["manifest"]
            for name, data in self.plugins.items()
        }

    def get_logs(self):
        return self.logs

    def validate_dependencies(self):
        missing = []

        for plugin_name, plugin_data in self.plugins.items():
            manifest = plugin_data["manifest"]

            for required in manifest.get("requires", []):
                if required not in self.capabilities:
                    missing.append({
                        "plugin": plugin_name,
                        "missing": required
                    })

        return missing

    def get_config(self):
        return self.config_manager.get()

    def update_config(self, key, value):
        self.config_manager.update(key, value)

    def get_active_profile(self):
        return self.config_manager.get_active_profile()


    def get_all_profiles(self):
        return self.config_manager.get_all_profiles()


    def create_profile(self, profile_name):
        return self.config_manager.create_profile(
            profile_name
        )


    def set_active_profile(self, profile_name):
        return self.config_manager.set_active_profile(
            profile_name
        )


    def update_profile_value(
        self,
        key,
        value
    ):
        return self.config_manager.update_profile_value(
            key,
            value
        )


    def update_plugin_state(
        self,
        plugin_name,
        enabled
    ):
        return self.config_manager.update_plugin_state(
            plugin_name,
            enabled
        )

    def get_api_key(self, service_name):
        profile = self.get_active_profile()
        return profile.get(
            "api_keys",
            {}
        ).get(
            service_name,
            ""
        )


    def update_api_key(
        self,
        service_name,
        value
    ):
        profile = self.get_active_profile()

        if "api_keys" not in profile:
            profile["api_keys"] = {}

        profile["api_keys"][service_name] = value
        self.config_manager.save()
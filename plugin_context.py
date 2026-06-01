class PluginContext:
    def __init__(self, host):
        self.host = host

    def request(self, capability, payload, metadata=None):
        return self.host.request(
            capability,
            payload,
            metadata
        )

    def publish(self,event_name,payload,metadata=None):
        return

    def subscribe(self, event_name, plugin_name):
        return self.host.subscribe_event(
            event_name,
            plugin_name
        )

    def get_config(self):
        return self.host.get_config()


    def update_config(self, key, value):
        return self.host.update_config(key, value)

    def get_active_profile(self):
        return self.host.get_active_profile()


    def get_all_profiles(self):
        return self.host.get_all_profiles()


    def create_profile(self, profile_name):
        return self.host.create_profile(
            profile_name
        )


    def set_active_profile(self, profile_name):
        return self.host.set_active_profile(
            profile_name
        )


    def update_profile_value(
        self,
        key,
        value
    ):
        return self.host.update_profile_value(
            key,
            value
        )


    def update_plugin_state(
        self,
        plugin_name,
        enabled
    ):
        return self.host.update_plugin_state(
            plugin_name,
            enabled
        )


    def get_api_key(
        self,
        service_name
    ):
        return self.host.get_api_key(
            service_name
        )


    def update_api_key(
        self,
        service_name,
        value
    ):
        return self.host.update_api_key(
            service_name,
            value
        )
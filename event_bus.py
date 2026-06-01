class EventBus:
    def __init__(self):
        self.subscribers = {}
        self.event_log = []

    def subscribe(self, event_name, plugin_name):
        if event_name not in self.subscribers:
            self.subscribers[event_name] = []

        if plugin_name not in self.subscribers[event_name]:
            self.subscribers[event_name].append(plugin_name)

    def publish(self, event_name, payload):
        self.event_log.append({
            "event": event_name,
            "payload": payload
        })

        return self.subscribers.get(event_name, [])

    def get_subscribers(self):
        return self.subscribers

    def get_event_log(self):
        return self.event_log
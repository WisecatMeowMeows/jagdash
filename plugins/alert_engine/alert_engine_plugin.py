def manifest():
    return {
        "name": "alert_engine",
        "version": "1.0",
        "provides": [],
        "requires": [],
        "subscribes": [
            "market.tick"
        ]
    }


def handle_event(event_name, payload, context):
    price = payload.get("price")

    if price > 105000:
        return {
            "alert": "BTC price exceeded threshold"
        }

    return {
        "alert": "No action"
    }
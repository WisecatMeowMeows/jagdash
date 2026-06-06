# c0rdin8/plugin.py
# Coordinated Signal Feed Plugin for NiteTrader

import requests


DEFAULT_FEEDS = [
    "http://127.0.0.1:5000/feed/wsb.json",
    "http://127.0.0.1:5000/feed/crypto.json",
]



def manifest():
    return {
        "name": "c0rdin8",
        "version": "1.0",
        "provides": [
            "feed.fetch",
            "feed.fetch_all"
        ],
        "requires": []
    }


def _handle_feed_fetch(payload, context):

    url = payload.get("feed_url")

    if not url:
        return {
            "status": "error",
            "message": "feed_url missing"
        }

    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()

        data = r.json()

        return {
            "status": "success",
            "feed": {
                "feed_id": data.get("feed_id"),
                "feed_name": data.get("feed_name"),
                "publisher": data.get("publisher"),
                "signal_count": data.get("signal_count", 0),
            },
            "data": data.get("signals", [])
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

def _handle_fetch_all(payload, context):

    all_signals = []

    for url in DEFAULT_FEEDS:

        try:

            r = requests.get(url, timeout=5)
            r.raise_for_status()

            data = r.json()

            for signal in data.get("signals", []):
                signal["_feed_name"] = data.get("feed_name")
                all_signals.append(signal)

        except Exception:
            pass

    return {
        "status": "success",
        "data": all_signals
    }

def handle_request(request, context):

    capability = request.get("capability")
    payload = request.get("payload", {})

    if capability == "feed.fetch":
        return _handle_feed_fetch(payload, context)

    if capability == "feed.fetch_all":
        return _handle_fetch_all(payload, context)

    return {
        "status": "error",
        "message": f"Unsupported capability: {capability}"
    }


""" #old version
import requests
import time

DEFAULT_TIMEOUT = 5
DEFAULT_POLL_INTERVAL = 30

FEEDS_KEY = "c0rdin8_feeds_cache"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def manifest():
    return {
        "name": "c0rdin8",
        "version": "1.0",
        "provides": [
            "feed.signal.latest",
            "feed.signal.history",
            "feed.feed.list",
            "feed.feed.sync",
        ],
        "requires": []
    }


# ---------------------------------------------------------------------------
# Internal storage helpers
# ---------------------------------------------------------------------------

def _get_cache(context):
    if not hasattr(context, "state"):
        context.state = {}
    return context.state.setdefault(FEEDS_KEY, {
        "feeds": {},
        "signals": []
    })


def _store_signals(cache, feed_id, signals):
    for s in signals:
        s["_received_at"] = time.time()
        s["_feed_id"] = feed_id
        cache["signals"].append(s)


def _load_feed(url):
    try:
        r = requests.get(url, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None


# ---------------------------------------------------------------------------
# Sync logic
# ---------------------------------------------------------------------------

def _sync_feeds(context):
    cache = _get_cache(context)

    feeds = cache["feeds"]

    all_new = []

    for feed_id, feed in feeds.items():
        if not feed.get("enabled", True):
            continue

        url = feed.get("url")
        if not url:
            continue

        data = _load_feed(url)
        if not data:
            continue

        # expected: list[signals]
        if isinstance(data, dict):
            data = data.get("signals", [])

        _store_signals(cache, feed_id, data)
        all_new.extend(data)

    return all_new


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

def _handle_feed_list(context):
    cache = _get_cache(context)

    return {
        "status": "success",
        "data": cache["feeds"]
    }


def _handle_feed_sync(context):
    signals = _sync_feeds(context)

    for s in signals:
        context.publish("feed.signal.received", s)

    return {
        "status": "success",
        "data": {
            "new_signals": len(signals)
        }
    }


def _handle_signal_latest(context):
    cache = _get_cache(context)

    if not cache["signals"]:
        return {"status": "success", "data": None}

    return {
        "status": "success",
        "data": cache["signals"][-1]
    }


def _handle_signal_history(payload, context):
    cache = _get_cache(context)

    limit = payload.get("limit", 100)

    return {
        "status": "success",
        "data": cache["signals"][-limit:]
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def handle_request(request, context):
    capability = request.get("capability")
    payload = request.get("payload", {})

    if capability == "feed.feed.list":
        return _handle_feed_list(context)

    if capability == "feed.feed.sync":
        return _handle_feed_sync(context)

    if capability == "feed.signal.latest":
        return _handle_signal_latest(context)

    if capability == "feed.signal.history":
        return _handle_signal_history(payload, context)

    return {
        "status": "error",
        "message": f"Unsupported capability: {capability}"
    }
    """
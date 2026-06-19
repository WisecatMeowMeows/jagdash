def manifest():
    return {
        "name": "news_feed",
        "version": "1.0",
        "provides": ["news.headlines"],
        "requires": []
    }


def handle_request(request, context):
    symbol = request["payload"].get("symbol", "BTC")

    return {
        "status": "success",
        "data": {
            "headlines": [
                f"{symbol} jumps after ETF rumors",
                f"{symbol} traders watch Fed decision"
            ]
        }
    }
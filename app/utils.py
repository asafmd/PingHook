import json
import time
from collections import defaultdict
from typing import Dict, Tuple

# Rate Limiter
# Simple in-memory token bucket or fixed window.
# We'll use a Fixed Window counter for simplicity.
# structure: {user_api_key: (timestamp_minute_start, count)}

_rate_limit_store: Dict[str, Tuple[int, int]] = defaultdict(lambda: (0, 0))
RATE_LIMIT_REQUESTS = 5
RATE_LIMIT_WINDOW = 60 # seconds

def is_rate_limited(api_key: str) -> bool:
    """
    Returns True if the user is rate limited.
    """
    current_time = int(time.time())
    window_start, count = _rate_limit_store[api_key]
    
    if current_time - window_start > RATE_LIMIT_WINDOW:
        # New window
        _rate_limit_store[api_key] = (current_time, 1)
        return False
    
    if count >= RATE_LIMIT_REQUESTS:
        return True
    
    _rate_limit_store[api_key] = (window_start, count + 1)
    return False

# Message Formatter
def format_message(
    data: dict | str | None,
    labels: list[str] | None = None
) -> str:
    """
    Formats the incoming webhook data into a readable Telegram message.
    """
    labels = labels or []

    # ---- Label header (NEW, optional) ----
    label_text = ""
    if labels:
        label_text = f"📍 <b>Source:</b> {' / '.join(labels)}\n\n"

    # ---- Empty payload ----
    if data is None:
        return f"{label_text}<i>Received empty payload.</i>"

    # ---- String payload ----
    if isinstance(data, str):
        safe_text = data.replace("<", "&lt;").replace(">", "&gt;")
        return (
            "<b>New Webhook Received</b>\n\n"
            f"{label_text}"
            f"{safe_text}"
        )

    # ---- Dict / JSON payload ----
    if isinstance(data, dict):
        import json
        pretty_json = json.dumps(data, indent=2)
        safe_json = pretty_json.replace("<", "&lt;").replace(">", "&gt;")

        return (
            "<b>New Webhook Received</b>\n\n"
            f"{label_text}"
            f"<pre>{safe_json}</pre>"
        )

    # ---- Fallback ----
    return f"{label_text}<i>Unsupported payload format.</i>"


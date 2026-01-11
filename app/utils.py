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
def format_message(data: dict | str | None) -> str:
    """
    Formats the incoming webhook data into a readable Telegram message.
    """
    if data is None:
        return "<i>Received empty payload.</i>"

    if isinstance(data, str):
        # Escape HTML special chars just in case (basic)
        safe_text = data.replace("<", "&lt;").replace(">", "&gt;")
        return f"<b>New Webhook Received:</b>\n\n{safe_text}"
    
    if isinstance(data, dict):
        # Pretty print JSON
        try:
            formatted_json = json.dumps(data, indent=2, ensure_ascii=False)
            # Escape for HTML
            safe_json = formatted_json.replace("<", "&lt;").replace(">", "&gt;")
            return f"<b>New Webhook Received:</b>\n<pre><code class='language-json'>{safe_json}</code></pre>"
        except Exception:
            return f"<b>New Webhook Received:</b>\n\n{str(data)}"
            
    return "<i>Received unknown data format.</i>"

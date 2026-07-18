import logging
from datetime import datetime, timezone

from app.database import (
    get_or_create_rate_limit,
    reset_hourly,
    reset_daily,
    increment_rate_counters,
)

logger = logging.getLogger(__name__)

FREE_HOURLY_LIMIT = 100
FREE_DAILY_LIMIT  = 1_000
PRO_HOURLY_LIMIT  = 1_000
PRO_DAILY_LIMIT   = 10_000


def _parse_ts(ts_str: str) -> datetime:
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


async def check_rate_limit(api_key: str, is_pro: bool = False) -> tuple[bool, str]:
    """Returns (allowed, resets_in). resets_in is '' when allowed."""
    hourly_limit = PRO_HOURLY_LIMIT if is_pro else FREE_HOURLY_LIMIT
    daily_limit  = PRO_DAILY_LIMIT  if is_pro else FREE_DAILY_LIMIT

    record = await get_or_create_rate_limit(api_key)
    if not record:
        return True, ""  # fail open on DB error

    now         = datetime.now(timezone.utc)
    last_hourly = _parse_ts(record["last_reset_hourly"])
    last_daily  = _parse_ts(record["last_reset_daily"])

    if (now - last_hourly).total_seconds() >= 3600:
        record = await reset_hourly(api_key, now) or record

    if (now - last_daily).days >= 1:
        record = await reset_daily(api_key, now) or record

    if record["requests_this_hour"] >= hourly_limit:
        elapsed   = (now - _parse_ts(record["last_reset_hourly"])).total_seconds()
        remaining = max(1, int((3600 - elapsed) / 60))
        return False, f"{remaining} minutes"

    if record["requests_today"] >= daily_limit:
        elapsed   = (now - _parse_ts(record["last_reset_daily"])).total_seconds()
        remaining = max(1, int((86400 - elapsed) / 3600))
        return False, f"{remaining} hours"

    await increment_rate_counters(api_key)
    return True, ""

import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta

from supabase import create_client, Client

from app.config import settings
from app.utils import relative_time

logger = logging.getLogger(__name__)

supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)


# ── Users ─────────────────────────────────────────────────────────────────────

async def create_user(platform: str, platform_id: str) -> dict | None:
    api_key = secrets.token_urlsafe(32)

    def _insert_user():
        return supabase.table("users").insert({"api_key": api_key}).execute()

    try:
        user_resp = await asyncio.to_thread(_insert_user)
    except Exception as e:
        logger.warning(f"[DB] create_user insert failed (possible duplicate): {e}")
        return await get_user_by_platform(platform, platform_id)

    if not user_resp.data:
        return None

    user = user_resp.data[0]

    def _insert_identity():
        return supabase.table("platform_identities").insert({
            "user_id":     user["id"],
            "platform":    platform,
            "platform_id": platform_id,
        }).execute()

    def _insert_channel():
        channel_type = "slack_native" if platform == "slack" else platform
        return supabase.table("channels").insert({
            "user_id":     user["id"],
            "type":        channel_type,
            "destination": platform_id,
            "label":       "this chat" if platform == "telegram" else platform,
        }).execute()

    try:
        await asyncio.to_thread(_insert_identity)
        await asyncio.to_thread(_insert_channel)
    except Exception as e:
        logger.error(f"[DB] create_user identity/channel insert failed: {e}")

    return user


async def get_user_by_platform(platform: str, platform_id: str) -> dict | None:
    def _query_identity():
        return (
            supabase.table("platform_identities")
            .select("user_id")
            .eq("platform", platform)
            .eq("platform_id", platform_id)
            .limit(1)
            .execute()
        )

    try:
        pi_resp = await asyncio.to_thread(_query_identity)
        if not pi_resp.data:
            return None
        user_id = pi_resp.data[0]["user_id"]
    except Exception as e:
        logger.error(f"[DB] get_user_by_platform identity query failed: {e}")
        return None

    def _query_user():
        return (
            supabase.table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query_user)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] get_user_by_platform user query failed: {e}")
        return None


async def get_user_by_api_key(api_key: str) -> dict | None:
    def _query():
        return (
            supabase.table("users")
            .select("*")
            .eq("api_key", api_key)
            .limit(1)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] get_user_by_api_key failed: {e}")
        return None


async def update_api_key(user_id: str, new_key: str):
    def _update():
        return supabase.table("users").update({"api_key": new_key}).eq("id", user_id).execute()

    try:
        await asyncio.to_thread(_update)
    except Exception as e:
        logger.error(f"[DB] update_api_key failed: {e}")


# ── Channels ──────────────────────────────────────────────────────────────────

async def get_channels(user_id: str) -> list[dict]:
    def _query():
        return (
            supabase.table("channels")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("created_at")
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data or []
    except Exception as e:
        logger.error(f"[DB] get_channels failed: {e}")
        return []


async def save_channel(
    user_id: str,
    channel_type: str,
    destination: str,
    label: str | None,
) -> dict | None:
    def _insert():
        return supabase.table("channels").insert({
            "user_id":     user_id,
            "type":        channel_type,
            "destination": destination,
            "label":       label,
        }).execute()

    try:
        resp = await asyncio.to_thread(_insert)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] save_channel failed: {e}")
        return None


async def deactivate_channel(channel_id: str):
    def _update():
        return supabase.table("channels").update({"is_active": False}).eq("id", channel_id).execute()

    try:
        await asyncio.to_thread(_update)
    except Exception as e:
        logger.error(f"[DB] deactivate_channel failed: {e}")


# ── Alerting rules ────────────────────────────────────────────────────────────

async def get_active_rules(user_id: str) -> list[dict]:
    def _query():
        return (
            supabase.table("alerting_rules")
            .select("*")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .order("created_at")
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data or []
    except Exception as e:
        logger.error(f"[DB] get_active_rules failed: {e}")
        return []


async def add_rule(user_id: str, rule_type: str, config: dict):
    def _insert():
        return supabase.table("alerting_rules").insert({
            "user_id":   user_id,
            "rule_type": rule_type,
            "config":    config,
        }).execute()

    try:
        await asyncio.to_thread(_insert)
    except Exception as e:
        logger.error(f"[DB] add_rule failed: {e}")


async def remove_rule(user_id: str, rule_number: str) -> bool:
    try:
        n = int(rule_number)
    except ValueError:
        return False

    rules = await get_active_rules(user_id)
    if n < 1 or n > len(rules):
        return False

    rule_id = rules[n - 1]["id"]

    def _delete():
        return supabase.table("alerting_rules").delete().eq("id", rule_id).execute()

    try:
        await asyncio.to_thread(_delete)
        return True
    except Exception as e:
        logger.error(f"[DB] remove_rule failed: {e}")
        return False


async def clear_rules(user_id: str):
    def _delete():
        return supabase.table("alerting_rules").delete().eq("user_id", user_id).execute()

    try:
        await asyncio.to_thread(_delete)
    except Exception as e:
        logger.error(f"[DB] clear_rules failed: {e}")


# ── Rate limits ───────────────────────────────────────────────────────────────

async def get_or_create_rate_limit(api_key: str) -> dict | None:
    def _select():
        return (
            supabase.table("rate_limits")
            .select("*")
            .eq("api_key", api_key)
            .limit(1)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_select)
        if resp.data:
            return resp.data[0]
    except Exception as e:
        logger.error(f"[DB] get_or_create_rate_limit select failed: {e}")
        return None

    now = datetime.now(timezone.utc).isoformat()

    def _insert():
        return supabase.table("rate_limits").insert({
            "api_key":            api_key,
            "requests_today":     0,
            "requests_this_hour": 0,
            "last_reset_daily":   now,
            "last_reset_hourly":  now,
        }).execute()

    try:
        resp = await asyncio.to_thread(_insert)
        return resp.data[0] if resp.data else None
    except Exception:
        # Race condition — row created by a concurrent request
        try:
            resp = await asyncio.to_thread(_select)
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(f"[DB] get_or_create_rate_limit retry failed: {e}")
            return None


async def reset_hourly(api_key: str, now: datetime) -> dict | None:
    def _update():
        return supabase.table("rate_limits").update({
            "requests_this_hour": 0,
            "last_reset_hourly":  now.isoformat(),
        }).eq("api_key", api_key).execute()

    try:
        resp = await asyncio.to_thread(_update)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] reset_hourly failed: {e}")
        return None


async def reset_daily(api_key: str, now: datetime) -> dict | None:
    def _update():
        return supabase.table("rate_limits").update({
            "requests_today":    0,
            "last_reset_daily":  now.isoformat(),
        }).eq("api_key", api_key).execute()

    try:
        resp = await asyncio.to_thread(_update)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] reset_daily failed: {e}")
        return None


async def increment_rate_counters(api_key: str):
    def _rpc():
        return supabase.rpc("increment_rate_counters", {"p_api_key": api_key}).execute()

    try:
        await asyncio.to_thread(_rpc)
    except Exception as e:
        logger.error(f"[DB] increment_rate_counters failed: {e}")


# ── Dedup ─────────────────────────────────────────────────────────────────────

async def check_dedup_window(user_id: str, label: str, window_minutes: int) -> bool:
    """Returns True if label was successfully delivered within window_minutes."""
    ts = await get_dedup_timestamp(user_id, label)
    if ts is None:
        return False
    elapsed = (datetime.now(timezone.utc) - ts).total_seconds() / 60
    return elapsed < window_minutes


async def get_dedup_timestamp(user_id: str, label: str) -> datetime | None:
    def _query():
        return (
            supabase.table("dedup_log")
            .select("last_sent")
            .eq("user_id", user_id)
            .eq("label", label)
            .limit(1)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query)
        if resp.data:
            return datetime.fromisoformat(resp.data[0]["last_sent"].replace("Z", "+00:00"))
        return None
    except Exception as e:
        logger.error(f"[DB] get_dedup_timestamp failed: {e}")
        return None


async def update_dedup_log(user_id: str, label: str):
    def _upsert():
        return supabase.table("dedup_log").upsert({
            "user_id":   user_id,
            "label":     label,
            "last_sent": datetime.now(timezone.utc).isoformat(),
        }).execute()

    try:
        await asyncio.to_thread(_upsert)
    except Exception as e:
        logger.error(f"[DB] update_dedup_log failed: {e}")


# ── Usage logs ────────────────────────────────────────────────────────────────

async def log_usage(
    api_key: str,
    label: str,
    payload_size: int,
    status: str,
    suppressed_by: str | None,
    channels_notified: int,
    payload: str | None = None,
):
    def _insert():
        return supabase.table("usage_logs").insert({
            "api_key":           api_key,
            "label":             label,
            "payload_size":      payload_size,
            "status":            status,
            "suppressed_by":     suppressed_by,
            "channels_notified": channels_notified,
            "payload":           payload,
        }).execute()

    try:
        await asyncio.to_thread(_insert)
    except Exception as e:
        logger.error(f"[DB] log_usage failed: {e}")


async def get_recent_webhooks(api_key: str, limit: int = 10) -> list[dict]:
    def _query():
        return (
            supabase.table("usage_logs")
            .select("id,label,payload,created_at,channels_notified")
            .eq("api_key", api_key)
            .eq("status", "success")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data or []
    except Exception as e:
        logger.error(f"[DB] get_recent_webhooks failed: {e}")
        return []


async def get_usage_stats(api_key: str) -> dict:
    now         = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    week_start  = (now - timedelta(days=7)).isoformat()

    def _total():
        return supabase.table("usage_logs").select("id", count="exact").eq("api_key", api_key).execute()

    def _today():
        return (
            supabase.table("usage_logs")
            .select("id", count="exact")
            .eq("api_key", api_key)
            .gte("created_at", today_start)
            .execute()
        )

    def _suppressed():
        return (
            supabase.table("usage_logs")
            .select("id", count="exact")
            .eq("api_key", api_key)
            .eq("status", "suppressed")
            .gte("created_at", today_start)
            .execute()
        )

    def _week():
        return (
            supabase.table("usage_logs")
            .select("id", count="exact")
            .eq("api_key", api_key)
            .gte("created_at", week_start)
            .execute()
        )

    def _last():
        return (
            supabase.table("usage_logs")
            .select("created_at,label")
            .eq("api_key", api_key)
            .eq("status", "success")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )

    try:
        total_r = await asyncio.to_thread(_total)
        today_r = await asyncio.to_thread(_today)
        supp_r  = await asyncio.to_thread(_suppressed)
        week_r  = await asyncio.to_thread(_week)
        last_r  = await asyncio.to_thread(_last)
    except Exception as e:
        logger.error(f"[DB] get_usage_stats failed: {e}")
        return {"today": 0, "suppressed_today": 0, "this_week": 0, "total": 0,
                "last_ping_ago": "never", "last_label": "—"}

    last_ping_ago = "never"
    last_label    = "—"
    if last_r.data:
        last_ping_ago = relative_time(last_r.data[0]["created_at"])
        last_label    = last_r.data[0]["label"] or "—"

    return {
        "today":           today_r.count or 0,
        "suppressed_today": supp_r.count or 0,
        "this_week":       week_r.count or 0,
        "total":           total_r.count or 0,
        "last_ping_ago":   last_ping_ago,
        "last_label":      last_label,
    }


# ── Admin stats ───────────────────────────────────────────────────────────────

async def count_active_users(days: int) -> int:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    def _query():
        return (
            supabase.table("usage_logs")
            .select("api_key")
            .eq("status", "success")
            .gte("created_at", since)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query)
        return len({row["api_key"] for row in (resp.data or [])})
    except Exception as e:
        logger.error(f"[DB] count_active_users failed: {e}")
        return 0


async def count_pings_today() -> int:
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()

    def _query():
        return (
            supabase.table("usage_logs")
            .select("id", count="exact")
            .gte("created_at", today_start)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query)
        return resp.count or 0
    except Exception as e:
        logger.error(f"[DB] count_pings_today failed: {e}")
        return 0


async def count_all_pings() -> int:
    def _query():
        return supabase.table("usage_logs").select("id", count="exact").execute()

    try:
        resp = await asyncio.to_thread(_query)
        return resp.count or 0
    except Exception as e:
        logger.error(f"[DB] count_all_pings failed: {e}")
        return 0


# ── Web auth ──────────────────────────────────────────────────────────────────

async def get_user_by_id(user_id: str) -> dict | None:
    def _query():
        return supabase.table("users").select("*").eq("id", user_id).limit(1).execute()

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] get_user_by_id failed: {e}")
        return None


async def get_user_by_email(email: str) -> dict | None:
    def _query():
        return supabase.table("users").select("*").eq("email", email).limit(1).execute()

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] get_user_by_email failed: {e}")
        return None


async def get_user_by_google_id(google_id: str) -> dict | None:
    def _query():
        return supabase.table("users").select("*").eq("google_id", google_id).limit(1).execute()

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] get_user_by_google_id failed: {e}")
        return None


async def get_user_by_github_id(github_id: str) -> dict | None:
    def _query():
        return supabase.table("users").select("*").eq("github_id", github_id).limit(1).execute()

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] get_user_by_github_id failed: {e}")
        return None


async def create_web_user(email: str, password_hash: str) -> dict | None:
    api_key = secrets.token_urlsafe(32)

    def _insert():
        return supabase.table("users").insert({
            "api_key":       api_key,
            "email":         email,
            "password_hash": password_hash,
        }).execute()

    try:
        resp = await asyncio.to_thread(_insert)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] create_web_user failed: {e}")
        return None


async def link_email_to_user(user_id: str, email: str, password_hash: str) -> bool:
    def _update():
        return supabase.table("users").update({
            "email":         email,
            "password_hash": password_hash,
        }).eq("id", user_id).execute()

    try:
        await asyncio.to_thread(_update)
        return True
    except Exception as e:
        logger.error(f"[DB] link_email_to_user failed: {e}")
        return False


async def link_google_to_user(user_id: str, google_id: str, email: str | None) -> bool:
    updates: dict = {"google_id": google_id}
    if email:
        updates["email"] = email

    def _update():
        return supabase.table("users").update(updates).eq("id", user_id).execute()

    try:
        await asyncio.to_thread(_update)
        return True
    except Exception as e:
        logger.error(f"[DB] link_google_to_user failed: {e}")
        return False


async def link_github_to_user(user_id: str, github_id: str, email: str | None) -> bool:
    updates: dict = {"github_id": github_id}
    if email:
        updates["email"] = email

    def _update():
        return supabase.table("users").update(updates).eq("id", user_id).execute()

    try:
        await asyncio.to_thread(_update)
        return True
    except Exception as e:
        logger.error(f"[DB] link_github_to_user failed: {e}")
        return False


async def create_oauth_user(provider: str, provider_id: str, email: str | None) -> dict | None:
    api_key = secrets.token_urlsafe(32)
    data: dict = {"api_key": api_key, f"{provider}_id": provider_id}
    if email:
        data["email"] = email

    def _insert():
        return supabase.table("users").insert(data).execute()

    try:
        resp = await asyncio.to_thread(_insert)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] create_oauth_user failed: {e}")
        return None


# ── Pro tier ──────────────────────────────────────────────────────────────────

async def set_pro_status(
    user_id: str,
    is_pro: bool,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    pro_expires_at: str | None = None,
) -> bool:
    updates: dict = {"is_pro": is_pro}
    if stripe_customer_id:
        updates["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id:
        updates["stripe_subscription_id"] = stripe_subscription_id
    if pro_expires_at:
        updates["pro_expires_at"] = pro_expires_at

    def _update():
        return supabase.table("users").update(updates).eq("id", user_id).execute()

    try:
        await asyncio.to_thread(_update)
        return True
    except Exception as e:
        logger.error(f"[DB] set_pro_status failed: {e}")
        return False


async def get_user_by_stripe_customer(customer_id: str) -> dict | None:
    def _query():
        return (
            supabase.table("users")
            .select("*")
            .eq("stripe_customer_id", customer_id)
            .limit(1)
            .execute()
        )

    try:
        resp = await asyncio.to_thread(_query)
        return resp.data[0] if resp.data else None
    except Exception as e:
        logger.error(f"[DB] get_user_by_stripe_customer failed: {e}")
        return None


# ── BYOK AI keys ──────────────────────────────────────────────────────────────

async def save_ai_key(user_id: str, provider: str, key: str) -> bool:
    """Merge provider key into the ai_keys JSONB column."""
    user = await get_user_by_id(user_id)
    if not user:
        return False

    existing = user.get("ai_keys") or {}
    existing[provider] = key

    def _update():
        return supabase.table("users").update({"ai_keys": existing}).eq("id", user_id).execute()

    try:
        await asyncio.to_thread(_update)
        return True
    except Exception as e:
        logger.error(f"[DB] save_ai_key failed: {e}")
        return False


async def remove_ai_key(user_id: str, provider: str | None = None) -> bool:
    """Remove one provider key or all keys."""
    if provider:
        user = await get_user_by_id(user_id)
        if not user:
            return False
        existing = dict(user.get("ai_keys") or {})
        existing.pop(provider, None)
        new_keys = existing
    else:
        new_keys = {}

    def _update():
        return supabase.table("users").update({"ai_keys": new_keys}).eq("id", user_id).execute()

    try:
        await asyncio.to_thread(_update)
        return True
    except Exception as e:
        logger.error(f"[DB] remove_ai_key failed: {e}")
        return False

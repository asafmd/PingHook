from supabase import create_client, Client
from app.config import settings
import uuid

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_KEY
)


async def create_user(chat_id: int):
    """
    Create a new PingHook user.
    Generates a unique api_key automatically.
    """

    data = {
        "chat_id": chat_id,
        "api_key": str(uuid.uuid4()),
    }

    try:
        response = (
            supabase
            .table("users")
            .insert(data)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    except Exception as e:
        print(f"[DB] create_user failed: {e}")
        return None


async def get_user_by_api_key(api_key: str):
    """
    Resolve webhook API key → user.
    Used by /webhook/{api_key}
    """

    try:
        response = (
            supabase
            .table("users")
            .select("*")
            .eq("api_key", api_key)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    except Exception as e:
        print(f"[DB] get_user_by_api_key failed: {e}")
        return None


async def get_user_by_chat_id(chat_id: int):
    try:
        response = (
            supabase
            .table("users")
            .select("*")
            .eq("chat_id", chat_id)
            .limit(1)
            .execute()
        )

        if response.data:
            return response.data[0]

        return None

    except Exception as e:
        print(f"[DB] get_user_by_chat_id failed: {e}")
        return None


async def log_webhook(user_id: str, message: str):
    """
    Persist webhook message for observability/debugging.
    """

    data = {
        "user_id": user_id,
        "message": message,
    }

    try:
        supabase.table("webhooks").insert(data).execute()
    except Exception as e:
        print(f"[DB] log_webhook failed: {e}")

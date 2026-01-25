from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties  # <-- new import

from app.config import settings
from app.database import create_user, get_user_by_chat_id

# Initialize Bot with DefaultBotProperties instead of parse_mode
bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)


dp = Dispatcher()

# --- Command handler ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    chat_id = message.chat.id

    user = await get_user_by_chat_id(chat_id)
    if not user:
        user = await create_user(chat_id)

    if not user:
        await message.answer("⚠️ Failed to create your account.")
        return

    api_key = user["api_key"]
    webhook_url = f"{settings.BASE_URL.rstrip('/')}/v1/user/send/{api_key}"

    await message.answer(
        "👋 <b>Welcome to PingHook</b>\n\n"
        "PingHook forwards webhooks, API events, and alerts "
        "directly to this Telegram chat — instantly.\n\n"

        "<b>🔗 Your Webhook URL</b>\n"
        f"<code>{webhook_url}</code>\n\n"

        "<b>How it works</b>\n"
        "• Send a <b>POST</b> request to the URL above\n"
        "• Any payload (JSON or text) is delivered here\n"
        "• No setup, no dashboards\n\n"

        "<b>Optional labels (recommended)</b>\n"
        "Add path segments after the URL to tag events by source or environment.\n\n"
        "<i>Example</i>\n"
        f"<code>{webhook_url}/github</code>\n"
        f"<code>{webhook_url}/n8n/prod</code>\n\n"

        "<b>What you’ll see in Telegram</b>\n"
        "📍 <b>Source:</b> n8n / prod\n"
        "🔔 New Webhook Received\n"
        "{ ...payload... }\n\n"

        "That’s it. Start sending events 🚀"

    )
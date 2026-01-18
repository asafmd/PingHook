from app.bot import bot
from app.config import settings
import asyncio

async def set_webhook():
    await bot.set_webhook(f"{settings.BASE_URL}/webhook/{bot.id}")
    await bot.session.close()

asyncio.run(set_webhook())

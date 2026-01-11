from fastapi import FastAPI, Request, HTTPException, Path
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.bot import bot, dp
from app.config import settings
from app.database import get_user_by_api_key
from app.utils import is_rate_limited, format_message
import logging
import asyncio
from contextlib import asynccontextmanager



# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")

# Lifecycle management for Bot Polling
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start bot polling in the background
    logger.info("Starting Telegram Bot Polling...")
    #polling_task = asyncio.create_task(dp.start_polling(bot))
    polling_task = asyncio.create_task(
    dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types()
    ))

    
    yield
    
    # Shutdown
    logger.info("Stopping Telegram Bot...")
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()

app = FastAPI(title="PingHook", version="1.0.0", lifespan=lifespan)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # We can pass variables if we want, like the bot username if we had it in config
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/send/{api_key}")
async def receive_webhook(
    request: Request,
    api_key: str = Path(..., description="Your unique API Key")
):
    # 1. Check Rate Limit
    if is_rate_limited(api_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    # 2. Validate User and API Key
    user = await get_user_by_api_key(api_key)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API Key.")
        
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User is inactive.")

    # 3. Parse Body
    try:
        content_type = request.headers.get("Content-Type", "")
        if "application/json" in content_type:
            body = await request.json()
        else:
            body = (await request.body()).decode("utf-8")
    except Exception:
        body = "Error parsing body"

    # 4. Format Message
    message_text = format_message(body)

    # 5. Send to Telegram
    # We use a background task logic mostly, but here we await it to ensure delivery before 200 OK?
    # Or fire and forget? "Instant Telegram notifications" -> await is better for feedback to sender.
    try:
        await bot.send_message(chat_id=user["chat_id"], text=message_text)
    except Exception as e:
        logger.error(f"Failed to send message: {e}")
        raise HTTPException(status_code=500, detail="Failed to forward message to Telegram.")

    return {"status": "ok", "message": "Notification sent."}

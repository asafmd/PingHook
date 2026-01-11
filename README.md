# PingHook 🪝

A simple MicroSaaS that turns Telegram into a webhook receiver. Get instant notifications in Telegram from any service.

## Features
- **Zero Config**: Just start the bot to get a URL.
- **Secure**: Unique API Key per user.
- **Versatile**: Supports JSON, Form Data, and raw Text.
- **Pretty**: Formats JSON nicely in Telegram.
- **Rate Limited**: Prevents spam (5 req/min).

## Tech Stack
- **Framework**: FastAPI (Python)
- **Bot**: Aiogram 3.x
- **Database**: Supabase (PostgreSQL)
- **Hosting**: Render (Recommended)

## Local Setup

1. **Clone & Install**
   ```bash
   git clone <repo>
   cd pinghook
   pip install -r requirements.txt
   ```

2. **Environment Variables**
   Create a `.env` file:
   ```ini
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   SUPABASE_URL=https://xyz.supabase.co
   SUPABASE_KEY=eyJh...
   BASE_URL=http://localhost:8000
   ```

3. **Database Setup**
   Run the SQL from `schema.sql` in your Supabase SQL Editor.

4. **Run**
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Test**
   - Open your bot in Telegram and click `/start`.
   - Copy the URL provided.
   - Run: `curl -X POST <URL> -d '{"msg": "It works!"}'`

## Deployment (Render)

1. **New Web Service**: Connect your GitHub repo.
2. **Build Command**: `pip install -r requirements.txt`
3. **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. **Environment Variables**: Add `TELEGRAM_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_KEY`, and `BASE_URL` (set `BASE_URL` to your Render URL, e.g. `https://pinghook.onrender.com`).

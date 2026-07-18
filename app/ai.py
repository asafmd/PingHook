import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY", "")

_MAX_PAYLOAD_CHARS = 2000

_PROMPT = """\
You are a technical alert analyst. A developer just received this webhook notification.

Current time: {now}
Alert label: "{label}"
Payload:
{payload}

Your job is to INTERPRET and EXPLAIN this alert — do not restate or paraphrase JSON field names and values.
- Convert any timestamps (ISO 8601 or Unix epoch) to plain English relative to the current time (e.g. "2 minutes ago", "yesterday at 5:30 PM UTC").
- If the payload contains an error, exception, or stack trace: identify the root cause and suggest a concrete resolution.
- Use the label only when the payload alone is insufficient to determine context.
- Choose one emoji that best fits the event and prefix the Summary with it:
  🔴 critical failures, outages, crashes
  🟡 warnings, degraded performance, high usage
  🟢 resolved, healthy, back online
  🎉 successful deployments, milestones, completed jobs
  🔔 general alerts and notifications
  💳 payment events
  🚀 deployments and releases
  🛑 terminated or stopped services

Write a triage card. No markdown, no bullet points, no extra text:
Summary: [emoji] [real-world interpretation of what happened and its impact]
Severity: [Critical / Warning / Info / Success]
HTTP [code]: [ONLY include this line if a 4xx or 5xx HTTP status code exists in the payload. Classify as "Client-side error" (4xx) or "Server-side error" (5xx) and explain what the specific code means in one sentence. Omit this line entirely for 2xx codes or if no HTTP status code is present.]
Suggested Next Step: [specific actionable steps — reference actual file names, services, error types, or values from the payload]

Never write vague phrases like "check your system", "review the logs", or "investigate the issue".\
"""


async def analyze_payload(
    label: str,
    payload: str,
    provider: str = "claude",
    user_ai_keys: dict | None = None,
) -> str | None:
    prompt = _PROMPT.format(
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        label=label or "(no label)",
        payload=payload[:_MAX_PAYLOAD_CHARS],
    )
    user_ai_keys = user_ai_keys or {}
    try:
        if provider == "deepseek":
            return await _call_deepseek(prompt, user_ai_keys.get("deepseek"))
        return await _call_claude(prompt, user_ai_keys.get("claude"))
    except Exception as e:
        logger.error(f"AI analysis failed [{provider}]: {e}")
        return None


async def _call_claude(prompt: str, user_key: str | None = None) -> str | None:
    key = user_key or _ANTHROPIC_API_KEY
    if not key:
        logger.warning("No Claude API key available — skipping AI analysis")
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.json().get("content", [{}])[0].get("text", "").strip()
        return text or None


async def _call_deepseek(prompt: str, user_key: str | None = None) -> str | None:
    key = user_key or _DEEPSEEK_API_KEY
    if not key:
        logger.warning("No DeepSeek API key available — skipping AI analysis")
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        text = (
            resp.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return text or None

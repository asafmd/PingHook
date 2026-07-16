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

Write a triage card with exactly 3 lines. No markdown, no bullet points, no extra text:
Summary: [interpret what this event means and its real-world impact — not a restatement of field names]
Severity: [Critical / Warning / Info]
Next step: [specific, actionable steps to investigate or resolve — reference file names, services, or error types from the payload]

Never write vague phrases like "check your system", "review the logs", or "investigate the issue".\
"""


async def analyze_payload(
    label: str,
    payload: str,
    provider: str = "claude",
) -> str | None:
    # TODO: gate on pro tier once paid tier is implemented
    prompt = _PROMPT.format(
        now=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        label=label or "(no label)",
        payload=payload[:_MAX_PAYLOAD_CHARS],
    )
    try:
        if provider == "deepseek":
            return await _call_deepseek(prompt)
        return await _call_claude(prompt)
    except Exception as e:
        logger.error(f"AI analysis failed [{provider}]: {e}")
        return None


async def _call_claude(prompt: str) -> str | None:
    if not _ANTHROPIC_API_KEY:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI analysis")
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": _ANTHROPIC_API_KEY,
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


async def _call_deepseek(prompt: str) -> str | None:
    if not _DEEPSEEK_API_KEY:
        logger.warning("DEEPSEEK_API_KEY not set — skipping AI analysis")
        return None
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {_DEEPSEEK_API_KEY}",
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

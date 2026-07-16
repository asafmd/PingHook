import logging
import os

import httpx

logger = logging.getLogger(__name__)

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
_DEEPSEEK_API_KEY  = os.getenv("DEEPSEEK_API_KEY", "")

_MAX_PAYLOAD_CHARS = 2000

_PROMPT = """\
You are a webhook alert triage assistant. A developer received this notification in their Slack or Telegram channel.

Alert label: "{label}"
Payload:
{payload}

Analyse the payload as your primary source. If the payload is insufficient to determine context, use the label as a hint.
If the payload contains an error or stack trace, identify the root cause and provide a brief resolution.

Write a triage card with exactly 3 lines. No markdown, no bullet points, no extra text:
Summary: [what happened — derived from payload content, specific values and error messages where present]
Severity: [Critical / Warning / Info]
Next step: [most actionable fix or investigation step based on the payload — under 15 words]

Never write vague statements like "check your system", "review the logs", or "investigate the error". If specifics cannot be determined, say so plainly.\
"""


async def analyze_payload(
    label: str,
    payload: str,
    provider: str = "claude",
) -> str | None:
    # TODO: gate on pro tier once paid tier is implemented
    prompt = _PROMPT.format(
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
                "max_tokens": 150,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.json().get("content", [{}])[0].get("text", "").strip()
        return _format_card(text) if text else None


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
                "max_tokens": 150,
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
        return _format_card(text) if text else None


def _format_card(text: str) -> str:
    return f"🤖 AI Triage\n{text}\n──────────────────"

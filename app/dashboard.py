import logging
import secrets

import httpx
import stripe
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import (
    hash_password,
    verify_password,
    get_session_user_id,
    login_response,
    logout_response,
)
from app.config import settings
from app.database import (
    get_user_by_id,
    get_user_by_api_key,
    get_user_by_email,
    get_user_by_google_id,
    create_web_user,
    create_oauth_user,
    link_email_to_user,
    link_google_to_user,
    get_channels,
    get_usage_stats,
    get_recent_webhooks,
    save_ai_key,
    remove_ai_key,
    set_pro_status,
    get_user_by_stripe_customer,
)

logger    = logging.getLogger(__name__)
router    = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO  = "https://www.googleapis.com/oauth2/v2/userinfo"


def _base_url() -> str:
    return settings.BASE_URL.rstrip("/")


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(url=path, status_code=303)


async def _get_dashboard_user(request: Request) -> dict | None:
    user_id = get_session_user_id(request)
    if not user_id:
        return None
    return await get_user_by_id(user_id)


# ── Auth pages ────────────────────────────────────────────────────────────────

@router.get("/auth/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if get_session_user_id(request):
        return _redirect("/dashboard")
    return templates.TemplateResponse("auth/login.html", {
        "request": request,
        "error":   error,
        "google_enabled": bool(settings.GOOGLE_CLIENT_ID),
    })


@router.post("/auth/login")
async def login_submit(
    request: Request,
    method:   str = Form(""),
    api_key:  str = Form(""),
    email:    str = Form(""),
    password: str = Form(""),
):
    if method == "apikey":
        if not api_key.strip():
            return _redirect("/auth/login?error=Enter+your+API+key")
        user = await get_user_by_api_key(api_key.strip())
        if not user:
            return _redirect("/auth/login?error=Invalid+API+key")
        return login_response(user["id"])

    if method == "email":
        if not email or not password:
            return _redirect("/auth/login?error=Email+and+password+required")
        user = await get_user_by_email(email.lower().strip())
        if not user or not user.get("password_hash"):
            return _redirect("/auth/login?error=No+account+with+that+email")
        if not verify_password(password, user["password_hash"]):
            return _redirect("/auth/login?error=Incorrect+password")
        return login_response(user["id"])

    return _redirect("/auth/login?error=Unknown+login+method")


@router.get("/auth/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = ""):
    if get_session_user_id(request):
        return _redirect("/dashboard")
    return templates.TemplateResponse("auth/register.html", {
        "request": request,
        "error":   error,
        "google_enabled": bool(settings.GOOGLE_CLIENT_ID),
    })


@router.post("/auth/register")
async def register_submit(
    request:     Request,
    email:       str = Form(""),
    password:    str = Form(""),
    existing_key: str = Form(""),
):
    email    = email.lower().strip()
    password = password.strip()
    existing_key = existing_key.strip()

    if not email or not password:
        return _redirect("/auth/register?error=Email+and+password+required")
    if len(password) < 8:
        return _redirect("/auth/register?error=Password+must+be+at+least+8+characters")

    existing_email_user = await get_user_by_email(email)
    if existing_email_user:
        return _redirect("/auth/register?error=Email+already+registered.+Log+in+instead.")

    pw_hash = hash_password(password)

    if existing_key:
        user = await get_user_by_api_key(existing_key)
        if not user:
            return _redirect("/auth/register?error=API+key+not+found")
        if user.get("email"):
            return _redirect("/auth/register?error=That+API+key+already+has+an+account")
        await link_email_to_user(user["id"], email, pw_hash)
        return login_response(user["id"])

    user = await create_web_user(email, pw_hash)
    if not user:
        return _redirect("/auth/register?error=Registration+failed.+Try+again.")
    return login_response(user["id"])


@router.get("/auth/logout")
async def logout():
    return logout_response()


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/auth/google")
async def google_login(request: Request):
    if not settings.GOOGLE_CLIENT_ID:
        return _redirect("/auth/login?error=Google+login+not+configured")
    state    = secrets.token_urlsafe(16)
    callback = f"{_base_url()}/auth/google/callback"
    params   = (
        f"client_id={settings.GOOGLE_CLIENT_ID}"
        f"&redirect_uri={callback}"
        f"&response_type=code"
        f"&scope=openid+email+profile"
        f"&state={state}"
        f"&access_type=offline"
    )
    response = RedirectResponse(url=f"{_GOOGLE_AUTH_URL}?{params}", status_code=303)
    response.set_cookie("oauth_state", state, httponly=True, max_age=300)
    return response


@router.get("/auth/google/callback")
async def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error or not code:
        return _redirect("/auth/login?error=Google+login+cancelled")

    callback = f"{_base_url()}/auth/google/callback"
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri":  callback,
            "grant_type":    "authorization_code",
        })
        if token_resp.status_code != 200:
            return _redirect("/auth/login?error=Google+token+exchange+failed")
        access_token = token_resp.json().get("access_token")

        info_resp = await client.get(
            _GOOGLE_USERINFO,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if info_resp.status_code != 200:
            return _redirect("/auth/login?error=Could+not+fetch+Google+profile")
        info     = info_resp.json()
        google_id = str(info.get("id", ""))
        email     = info.get("email", "")

    user = await get_user_by_google_id(google_id)
    if not user:
        user = await get_user_by_email(email) if email else None
        if user:
            await link_google_to_user(user["id"], google_id, email)
        else:
            user = await create_oauth_user("google", google_id, email)
    if not user:
        return _redirect("/auth/login?error=Google+sign-in+failed")
    return login_response(user["id"])



# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = await _get_dashboard_user(request)
    if not user:
        return _redirect("/auth/login")

    stats, channels, recent = await _load_dashboard_data(user)
    ai_keys = user.get("ai_keys") or {}

    return templates.TemplateResponse("dashboard.html", {
        "request":     request,
        "user":        user,
        "stats":       stats,
        "channels":    channels,
        "recent":      recent,
        "ai_keys":     ai_keys,
        "base_url":    _base_url(),
        "pro_price":   "$9/mo",
        "stripe_enabled": bool(settings.STRIPE_SECRET_KEY),
    })


async def _load_dashboard_data(user: dict):
    stats    = await get_usage_stats(user["api_key"])
    channels = await get_channels(user["id"])
    recent   = await get_recent_webhooks(user["api_key"], limit=10)
    return stats, channels, recent


# ── Dashboard actions ─────────────────────────────────────────────────────────

@router.post("/dashboard/ai-key")
async def dashboard_save_ai_key(
    request:  Request,
    provider: str = Form("claude"),
    key:      str = Form(""),
):
    user = await _get_dashboard_user(request)
    if not user:
        return _redirect("/auth/login")
    key = key.strip()
    if not key:
        return _redirect("/dashboard?tab=settings&error=Key+cannot+be+empty")
    await save_ai_key(user["id"], provider, key)
    return _redirect("/dashboard?tab=settings&saved=1")


@router.post("/dashboard/ai-key/remove")
async def dashboard_remove_ai_key(
    request:  Request,
    provider: str = Form(""),
):
    user = await _get_dashboard_user(request)
    if not user:
        return _redirect("/auth/login")
    await remove_ai_key(user["id"], provider or None)
    return _redirect("/dashboard?tab=settings&removed=1")


# ── Stripe ────────────────────────────────────────────────────────────────────

@router.post("/dashboard/billing/checkout")
async def billing_checkout(request: Request):
    user = await _get_dashboard_user(request)
    if not user:
        return _redirect("/auth/login")
    if not settings.STRIPE_SECRET_KEY:
        return _redirect("/dashboard?tab=billing&error=Billing+not+configured")

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
            customer_email=user.get("email") or None,
            client_reference_id=user["id"],
            success_url=f"{_base_url()}/dashboard?tab=billing&upgraded=1",
            cancel_url=f"{_base_url()}/dashboard?tab=billing",
        )
        return RedirectResponse(url=session.url, status_code=303)
    except Exception as e:
        logger.error(f"Stripe checkout failed: {e}")
        return _redirect("/dashboard?tab=billing&error=Checkout+failed.+Try+again.")


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    if not settings.STRIPE_SECRET_KEY:
        return {"ok": False}

    payload    = await request.body()
    sig_header = request.headers.get("Stripe-Signature", "")
    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning(f"Stripe webhook invalid: {e}")
        return {"ok": False}

    ev_type = event["type"]
    data    = event["data"]["object"]

    if ev_type == "checkout.session.completed":
        user_id     = data.get("client_reference_id")
        customer_id = data.get("customer")
        sub_id      = data.get("subscription")
        if user_id:
            await set_pro_status(
                user_id,
                is_pro=True,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
            )

    elif ev_type in ("customer.subscription.deleted", "customer.subscription.paused"):
        customer_id = data.get("customer")
        user        = await get_user_by_stripe_customer(customer_id)
        if user:
            await set_pro_status(user["id"], is_pro=False)

    elif ev_type == "customer.subscription.updated":
        customer_id = data.get("customer")
        status      = data.get("status")
        user        = await get_user_by_stripe_customer(customer_id)
        if user:
            await set_pro_status(user["id"], is_pro=(status == "active"))

    return {"ok": True}

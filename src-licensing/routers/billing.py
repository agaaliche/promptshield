"""Billing router — Stripe checkout sessions & webhook handling."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from config import settings
from database import get_db
from models import Subscription, User
from schemas import BillingPortalResponse, CheckoutRequest, CheckoutResponse, SubscriptionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

stripe.api_key = settings.stripe_secret_key


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout Session for a new subscription."""

    # Create Stripe customer if needed
    if not user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": str(user.id)},
        )
        user.stripe_customer_id = customer.id
        await db.flush()

    # Check for existing active subscription
    for sub in user.subscriptions:
        if sub.status in ("active", "trialing"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have an active subscription. Manage it from the billing portal.",
            )

    # Determine if eligible for trial
    trial_settings = {}
    if not user.trial_used:
        trial_settings["subscription_data"] = {
            "trial_period_days": settings.trial_days,
            "metadata": {"user_id": str(user.id)},
        }
    else:
        trial_settings["subscription_data"] = {
            "metadata": {"user_id": str(user.id)},
        }

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=user.stripe_customer_id,
        line_items=[{"price": settings.stripe_price_id_monthly, "quantity": 1}],
        success_url=body.success_url or f"{settings.frontend_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=body.cancel_url or f"{settings.frontend_url}/billing/cancel",
        **trial_settings,
    )

    return CheckoutResponse(checkout_url=session.url, session_id=session.id)


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook events.

    Events handled:
      - checkout.session.completed — create local Subscription
      - customer.subscription.updated — sync status changes
      - customer.subscription.deleted — mark canceled
      - invoice.payment_failed — mark past_due
    """
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    if not sig:
        raise HTTPException(status_code=400, detail="Missing stripe-signature header")

    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as exc:
        logger.error("Webhook error: %s", exc)
        raise HTTPException(status_code=400, detail="Webhook error")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data, db)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data, db)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, db)
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data, db)
    else:
        logger.info("Unhandled event type: %s", event_type)

    return {"ok": True}


async def _handle_checkout_completed(data: dict, db: AsyncSession):
    """Create a local Subscription when Stripe checkout succeeds."""
    stripe_sub_id = data.get("subscription")
    customer_id = data.get("customer")
    user_id_meta = data.get("metadata", {}).get("user_id") or (
        data.get("subscription_data", {}).get("metadata", {}).get("user_id")
    )

    if not stripe_sub_id or not customer_id:
        logger.warning("checkout.session.completed missing subscription or customer")
        return

    # Find user by stripe customer id
    result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.error("checkout.session.completed: user not found for customer %s", customer_id)
        return

    # Fetch subscription details from Stripe
    stripe_sub = stripe.Subscription.retrieve(stripe_sub_id)
    is_trial = stripe_sub.status == "trialing"

    sub = Subscription(
        user_id=user.id,
        stripe_subscription_id=stripe_sub_id,
        plan="free_trial" if is_trial and not user.trial_used else "pro",
        status=stripe_sub.status,
        seats=settings.max_seats_per_subscription,
        current_period_start=datetime.fromtimestamp(stripe_sub.current_period_start, tz=timezone.utc),
        current_period_end=datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc),
    )
    if is_trial and stripe_sub.trial_end:
        sub.trial_end = datetime.fromtimestamp(stripe_sub.trial_end, tz=timezone.utc)
        user.trial_used = True

    db.add(sub)
    await db.flush()
    logger.info("Subscription created for user %s (plan=%s, status=%s)", user.email, sub.plan, sub.status)


async def _handle_subscription_updated(data: dict, db: AsyncSession):
    """Sync subscription status changes from Stripe."""
    stripe_sub_id = data.get("id")
    if not stripe_sub_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        logger.warning("subscription.updated: local sub not found for %s", stripe_sub_id)
        return

    sub.status = data.get("status", sub.status)
    if data.get("current_period_start"):
        sub.current_period_start = datetime.fromtimestamp(data["current_period_start"], tz=timezone.utc)
    if data.get("current_period_end"):
        sub.current_period_end = datetime.fromtimestamp(data["current_period_end"], tz=timezone.utc)

    # Upgrade plan from trial to pro if no longer trialing
    if sub.plan == "free_trial" and sub.status == "active":
        sub.plan = "pro"

    await db.flush()
    logger.info("Subscription %s updated to status=%s", stripe_sub_id, sub.status)


async def _handle_subscription_deleted(data: dict, db: AsyncSession):
    """Mark local subscription as canceled."""
    stripe_sub_id = data.get("id")
    if not stripe_sub_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = "canceled"
        await db.flush()
        logger.info("Subscription %s canceled", stripe_sub_id)


async def _handle_payment_failed(data: dict, db: AsyncSession):
    """Mark subscription as past_due on payment failure."""
    stripe_sub_id = data.get("subscription")
    if not stripe_sub_id:
        return

    result = await db.execute(
        select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = "past_due"
        await db.flush()
        logger.info("Subscription %s marked past_due after payment failure", stripe_sub_id)


@router.get("/subscription", response_model=SubscriptionResponse | None)
async def get_subscription(user: User = Depends(get_current_user)):
    """Get the user's current subscription details."""
    for sub in sorted(user.subscriptions, key=lambda s: s.created_at, reverse=True):
        if sub.status in ("active", "trialing", "past_due"):
            return SubscriptionResponse(
                id=str(sub.id),
                plan=sub.plan,
                status=sub.status,
                seats=sub.seats,
                current_period_start=sub.current_period_start,
                current_period_end=sub.current_period_end,
                trial_end=sub.trial_end,
                created_at=sub.created_at,
            )
    return None


@router.post("/portal", response_model=BillingPortalResponse)
async def create_billing_portal(
    user: User = Depends(get_current_user),
):
    """Create a Stripe Customer Portal session for managing billing."""
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found")

    session = stripe.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.frontend_url}/settings",
    )

    return BillingPortalResponse(portal_url=session.url)

import time
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.models.database import get_db, User
from backend.models.payment import Payment, PaymentStatus, PaymentProvider
from backend.services.auth import get_current_user, get_optional_user
from backend.services.click_service import generate_payment_url
from backend.services.plans import PLANS, get_or_create_subscription
from backend.config import get_settings

router = APIRouter(prefix="/api/plans", tags=["plans"])


def _subscription_to_dict(sub) -> dict:
    return {
        "plan": sub.plan.value,
        "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        "videos_used_this_period": sub.videos_used_this_period,
    }


@router.get("")
def list_plans(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user),
) -> dict:
    # Narxlarni har kim ko'ra oladi (marketing/pricing sahifasi) — faqat
    # obuna bo'lish (subscribe) uchun login talab qilinadi.
    current = _subscription_to_dict(get_or_create_subscription(db, current_user.id)) if current_user else None
    return {
        "plans": [
            {
                "id": p.id, "name": p.name, "price": p.price,
                "videos_per_period": p.videos_per_period, "free_minutes": p.free_minutes,
                "priority": p.priority, "tts_tier": p.tts_tier,
                "tier": p.tier.value, "period_days": p.period_days,
                "max_resolution": p.max_resolution,
            }
            for p in PLANS.values()
        ],
        "current": current,
    }


class SubscribeRequest(BaseModel):
    plan: str


@router.post("/subscribe")
def subscribe(
    body: SubscribeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    plan_id = body.plan
    if plan_id not in PLANS or plan_id == "free":
        raise HTTPException(status_code=400, detail="Noto'g'ri tarif tanlandi.")

    settings = get_settings()
    plan = PLANS[plan_id]

    payment = Payment(
        user_id=current_user.id,
        plan=plan_id,
        amount=plan.price,
        provider=PaymentProvider.CLICK,
        status=PaymentStatus.PENDING,
        click_create_time=int(time.time()),
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)

    merchant_id = settings.CLICK_MERCHANT_ID or "56653"
    service_id = settings.CLICK_SERVICE_ID or "108780"
    merchant_user_id = getattr(settings, "CLICK_MERCHANT_USER_ID", "") or "89102"

    origin_header = request.headers.get("origin") or request.headers.get("referer")
    if origin_header:
        from urllib.parse import urlparse
        parsed = urlparse(origin_header)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
        return_url = f"{base_origin}/dashboard"
    else:
        frontend_url = settings.FRONTEND_URL or "https://gapirai.uz"
        return_url = f"{frontend_url.rstrip('/')}/dashboard"

    payment_url = generate_payment_url(
        merchant_id=merchant_id,
        service_id=service_id,
        transaction_param=str(payment.id),
        amount=plan.price,
        return_url=return_url,
        merchant_user_id=merchant_user_id,
    )

    return {"success": True, "payment_url": payment_url, "payment_id": str(payment.id), "amount": plan.price}

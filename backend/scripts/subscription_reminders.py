"""Obuna eslatma cron — muddati 3 kundan keyin tugaydigan obunalarga email yuboradi.

Ishlatish (kunlik cron, disk/health-check cron bilan bir xil naqsh):
    PYTHONPATH=. python -m backend.scripts.subscription_reminders
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.models.database import SessionLocal, Subscription, User, PlanTier
from backend.services.plans import PLANS
from backend.services.email_service import send_subscription_reminder_email

REMINDER_WINDOW_DAYS = 3


def main() -> int:
    db = SessionLocal()
    sent, skipped = 0, 0
    try:
        window_start = datetime.utcnow()
        window_end = window_start + timedelta(days=REMINDER_WINDOW_DAYS)

        expiring = (
            db.query(Subscription)
            .filter(Subscription.plan != PlanTier.FREE)
            .filter(Subscription.expires_at.isnot(None))
            .filter(Subscription.expires_at >= window_start)
            .filter(Subscription.expires_at <= window_end)
            .all()
        )

        for sub in expiring:
            user = db.query(User).filter(User.id == sub.user_id).first()
            if not user or not user.email:
                skipped += 1
                continue
            plan_name = PLANS[sub.plan.value].name
            expires_str = sub.expires_at.strftime("%Y-%m-%d")
            ok = send_subscription_reminder_email(user.email, user.name or "", plan_name, expires_str)
            sent += 1 if ok else 0
            skipped += 0 if ok else 1

        print(f"[subscription_reminders] {len(expiring)} ta obuna topildi, {sent} email yuborildi, {skipped} o'tkazib yuborildi.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

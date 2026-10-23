from fastapi import APIRouter

from app.api.v1 import audit_logs, auth, health, payment_occurrences, payments_summary, receipts, recurring_payments, users

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(recurring_payments.router)
router.include_router(payment_occurrences.router)
router.include_router(payments_summary.router)
router.include_router(users.router)
router.include_router(audit_logs.router)
router.include_router(receipts.router)

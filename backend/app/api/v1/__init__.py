from fastapi import APIRouter

from app.api.v1 import admin_tools, audit_logs, auth, budgets, health, payment_occurrences, payments_summary, receipts, recurring_payments, users, webhooks

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(recurring_payments.router)
router.include_router(payment_occurrences.router)
router.include_router(payments_summary.router)
router.include_router(users.router)
router.include_router(audit_logs.router)
router.include_router(receipts.router)
router.include_router(budgets.router)
router.include_router(webhooks.router)
router.include_router(admin_tools.router)

from fastapi import APIRouter

router = APIRouter(tags=["logistics-kpi"])

# Stub router.
# Purpose: prevent startup warnings "Skip router api.routers.logistics_kpi: ModuleNotFoundError"
# KPI endpoints are handled elsewhere for now.

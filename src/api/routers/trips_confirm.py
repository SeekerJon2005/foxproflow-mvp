from fastapi import APIRouter

router = APIRouter(tags=["trips-confirm"])

# Stub router.
# Purpose: prevent startup warnings "Skip router api.routers.trips_confirm: ModuleNotFoundError"
# Real implementation lives elsewhere (legacy/new confirm routers).

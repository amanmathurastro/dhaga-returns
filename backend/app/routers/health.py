from fastapi import APIRouter

from app import db
from app.config import get_settings
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(
        status="ok",
        database="ok" if db.ping() else "unreachable",
        openrouter_key_present=bool(get_settings().OPENROUTER_API_KEY),
    )

from fastapi import APIRouter

from app import db
from app.config import get_settings
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    problem = db.ping_problem()
    return HealthOut(
        status="ok",
        database="unreachable" if problem else "ok",
        database_problem=problem,
        openrouter_key_present=bool(get_settings().OPENROUTER_API_KEY),
    )

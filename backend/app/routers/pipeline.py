from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query

from app import db
from app.config import get_settings
from app.errors import ApiError
from app.pipeline.run import execute_run, run_params
from app.reporting import run_info
from app.schemas import DateRange, RunInfo, RunList, RunRequest, RunStarted

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run", response_model=RunStarted, status_code=202)
def start_run(background: BackgroundTasks, body: Optional[RunRequest] = None) -> RunStarted:
    body = body or RunRequest()
    settings = get_settings()
    with db.connect() as conn:
        run_id = db.create_run(
            conn,
            model_a_id=settings.MODEL_A_ID,
            model_b_id=settings.MODEL_B_ID,
            period_start=body.period_start,
            period_end=body.period_end,
            params=run_params(settings),
        )
    if run_id is None:
        raise ApiError(409, "run_in_progress", "A pipeline run is already in progress. Wait for it to finish.")
    background.add_task(execute_run, run_id, body.period_start, body.period_end)
    return RunStarted(run_id=str(run_id))


@router.get("/date-range", response_model=DateRange)
def date_range() -> DateRange:
    """The span of order dates in the data, used to pre-fill the period on the Run pipeline form."""
    with db.connect() as conn:
        row = db.order_date_range(conn)
    return DateRange(first_order_date=row["first"], last_order_date=row["last"])


@router.get("/runs", response_model=RunList)
def list_runs(limit: int = Query(10, ge=1, le=50)) -> RunList:
    with db.connect() as conn:
        return RunList(runs=[run_info(r) for r in db.list_runs(conn, limit)])


@router.get("/runs/{run_id}", response_model=RunInfo)
def get_run(run_id: UUID) -> RunInfo:
    with db.connect() as conn:
        run = db.get_run(conn, run_id)
    if run is None:
        raise ApiError(404, "run_not_found", "That pipeline run doesn't exist.")
    return run_info(run)

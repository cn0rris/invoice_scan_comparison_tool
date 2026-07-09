import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.db import compute_summary, db, new_id
from app.models.api_schemas import StartRunRequest, StartRunResponse
from app.orchestrator.checksum import compute_run_checksum
from app.orchestrator.runner import start_run

router = APIRouter()


def _resolve_under_root(raw: str | None, default: str) -> Path:
    candidate = Path(raw).resolve() if raw else Path(default).resolve()
    root = settings.data_root
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Directory '{raw}' must resolve under the mounted data root ({root})"
        )
    return candidate


@router.post("/api/runs", response_model=StartRunResponse)
async def create_run(body: StartRunRequest, request: Request):
    if not body.models:
        raise HTTPException(status_code=400, detail="At least one model must be selected")

    invoice_dir = _resolve_under_root(body.invoice_dir, settings.invoice_dir)
    ground_truth_dir = _resolve_under_root(body.ground_truth_dir, settings.ground_truth_dir)

    checksum = await compute_run_checksum(invoice_dir, ground_truth_dir, body.prompt, body.models)

    if not body.force:
        existing = await db.find_completed_run_by_checksum(checksum)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "An identical run (same invoices, ground truth, prompt, and models) already completed.",
                    "existing_run": existing,
                },
            )

    run_id = new_id()
    await db.create_run(run_id, body.prompt, str(invoice_dir), str(ground_truth_dir), body.models, checksum)

    task = asyncio.create_task(start_run(run_id, body.models, body.prompt, invoice_dir, ground_truth_dir))
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    return StartRunResponse(run_id=run_id)


@router.get("/api/runs")
async def list_runs(limit: int = 50):
    return await db.list_runs(limit)


@router.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    results = await db.get_results_for_run(run_id)
    return {"run": run, "results": results}


@router.get("/api/runs/{run_id}/summary")
async def get_run_summary(run_id: str):
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    results = await db.get_results_for_run(run_id)
    return compute_summary(run, results)

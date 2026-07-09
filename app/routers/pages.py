from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db import db
from app.models.invoice import generate_default_prompt
from app.providers.registry import ANTHROPIC_MODELS

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "active_page": "home",
            "default_prompt": generate_default_prompt(),
            "anthropic_models": ANTHROPIC_MODELS,
            "default_invoice_dir": settings.invoice_dir,
            "default_ground_truth_dir": settings.ground_truth_dir,
        },
    )


@router.get("/invoices")
async def invoices_page(request: Request):
    return templates.TemplateResponse(request, "invoices.html", {"active_page": "invoices"})


@router.get("/runs")
async def runs_page(request: Request):
    return templates.TemplateResponse(request, "runs.html", {"active_page": "runs"})


@router.get("/runs/{run_id}")
async def run_detail_page(request: Request, run_id: str):
    run = await db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return templates.TemplateResponse(
        request, "run_detail.html", {"active_page": "runs", "run_id": run_id, "run": run}
    )

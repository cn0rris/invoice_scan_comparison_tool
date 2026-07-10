from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.db import db
from app.models.invoice import generate_default_prompt
from app.providers.registry import ANTHROPIC_MODELS
from app.utils.files import INVOICE_EXTENSIONS, ground_truth_status

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


@router.get("/invoices/{filename}")
async def invoice_detail_page(request: Request, filename: str):
    invoice_dir = Path(settings.invoice_dir).resolve()
    ground_truth_dir = Path(settings.ground_truth_dir).resolve()
    safe_name = Path(filename).name  # strip any path components; defends against traversal
    file_path = invoice_dir / safe_name
    if safe_name != filename or file_path.suffix.lower() not in INVOICE_EXTENSIONS or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Invoice not found")

    gt_filename = f"{file_path.stem}.json"
    return templates.TemplateResponse(
        request,
        "invoice_detail.html",
        {
            "active_page": "invoices",
            "filename": safe_name,
            "filename_url": quote(safe_name),
            "is_pdf": file_path.suffix.lower() == ".pdf",
            "ground_truth_status": ground_truth_status(file_path, ground_truth_dir),
            "ground_truth_filename": gt_filename,
            "ground_truth_filename_url": quote(gt_filename),
        },
    )


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

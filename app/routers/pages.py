from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.config import settings
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
            "default_prompt": generate_default_prompt(),
            "anthropic_models": ANTHROPIC_MODELS,
            "default_invoice_dir": settings.invoice_dir,
            "default_ground_truth_dir": settings.ground_truth_dir,
        },
    )

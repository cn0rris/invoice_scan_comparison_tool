import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.models.invoice import InvoiceExtraction, generate_default_prompt
from app.providers.registry import get_provider
from app.utils.files import (
    INVOICE_EXTENSIONS,
    candidate_meta_path,
    candidate_path,
    describe_invoices,
    load_ground_truth_text,
)

router = APIRouter()

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class GenerateCandidateRequest(BaseModel):
    model_id: str


class CandidateContentRequest(BaseModel):
    content: str


def _resolve_invoice(filename: str) -> Path:
    """Traversal-safe lookup of an existing invoice file; 404s otherwise."""
    invoice_dir = Path(settings.invoice_dir).resolve()
    safe_name = Path(filename).name  # strip any path components; defends against traversal
    file_path = invoice_dir / safe_name
    if safe_name != filename or file_path.suffix.lower() not in INVOICE_EXTENSIONS or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Invoice not found")
    return file_path


def _candidate_paths(invoice_path: Path) -> tuple[Path, Path]:
    candidate_dir = Path(settings.ground_truth_candidate_dir).resolve()
    return candidate_path(invoice_path, candidate_dir), candidate_meta_path(invoice_path, candidate_dir)


def _load_candidate_meta(meta_file: Path) -> dict | None:
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text())
    except Exception:  # noqa: BLE001 - a corrupt meta sidecar shouldn't block viewing the candidate itself
        return None


@router.get("/api/invoices")
async def get_invoices():
    invoice_dir = Path(settings.invoice_dir).resolve()
    ground_truth_dir = Path(settings.ground_truth_dir).resolve()
    candidate_dir = Path(settings.ground_truth_candidate_dir).resolve()
    return describe_invoices(invoice_dir, ground_truth_dir, candidate_dir)


@router.get("/api/invoices/{filename}")
async def get_invoice_file(filename: str):
    invoice_dir = Path(settings.invoice_dir).resolve()
    safe_name = Path(filename).name  # strip any path components; defends against traversal
    file_path = invoice_dir / safe_name
    suffix = file_path.suffix.lower()
    if safe_name != filename or suffix not in INVOICE_EXTENSIONS or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Invoice not found")
    return FileResponse(
        file_path,
        media_type=_MEDIA_TYPES[suffix],
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.get("/api/ground-truth/{filename}")
async def get_ground_truth_file(filename: str):
    ground_truth_dir = Path(settings.ground_truth_dir).resolve()
    safe_name = Path(filename).name  # strip any path components; defends against traversal
    file_path = ground_truth_dir / safe_name
    if safe_name != filename or file_path.suffix.lower() != ".json" or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Ground truth file not found")
    return FileResponse(
        file_path,
        media_type="application/json",
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.post("/api/invoices")
async def upload_invoices(files: list[UploadFile]):
    invoice_dir = Path(settings.invoice_dir).resolve()
    invoice_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    skipped: list[dict] = []
    for upload in files:
        filename = Path(upload.filename or "").name  # strip any client-supplied path components
        suffix = Path(filename).suffix.lower()
        if not filename or suffix not in INVOICE_EXTENSIONS:
            skipped.append({"filename": filename or "(empty)", "reason": f"unsupported file type '{suffix}'"})
            continue
        dest = invoice_dir / filename
        if dest.exists():
            skipped.append({"filename": filename, "reason": "a file with this name already exists"})
            continue
        content = await upload.read()
        dest.write_bytes(content)
        saved.append(filename)

    return {"saved": saved, "skipped": skipped}


@router.get("/api/invoices/{filename}/candidate")
async def get_candidate(filename: str):
    invoice_path = _resolve_invoice(filename)
    cand_file, meta_file = _candidate_paths(invoice_path)
    if not cand_file.exists():
        raise HTTPException(status_code=404, detail="No candidate ground truth for this invoice")
    return {"content": cand_file.read_text(), "meta": _load_candidate_meta(meta_file)}


@router.post("/api/invoices/{filename}/candidate")
async def generate_candidate(filename: str, body: GenerateCandidateRequest):
    """Runs one extraction with the selected model and stores the result as a draft
    candidate awaiting human review. Regenerating over an existing candidate is
    allowed (the UI confirms first); overwriting approved ground truth is not."""
    invoice_path = _resolve_invoice(filename)
    ground_truth_dir = Path(settings.ground_truth_dir).resolve()
    if load_ground_truth_text(invoice_path, ground_truth_dir) is not None:
        raise HTTPException(
            status_code=409,
            detail="Approved ground truth already exists for this invoice. Delete it first to start over.",
        )

    provider = get_provider(body.model_id)
    result = await provider.extract(invoice_path, generate_default_prompt())
    if result.parsed is None:
        raise HTTPException(status_code=502, detail=f"Extraction failed: {result.error or 'no parsed output'}")

    cand_file, meta_file = _candidate_paths(invoice_path)
    cand_file.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(result.parsed, indent=2)
    meta = {
        "model_id": body.model_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": result.duration_ms,
    }
    cand_file.write_text(content)
    meta_file.write_text(json.dumps(meta, indent=2))
    return {"content": content, "meta": meta}


@router.put("/api/invoices/{filename}/candidate")
async def save_candidate(filename: str, body: CandidateContentRequest):
    """Saves an edited draft. Only JSON syntax is required here — full schema
    validation is deferred to approval so partial edits can be saved freely."""
    invoice_path = _resolve_invoice(filename)
    try:
        json.loads(body.content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Draft is not valid JSON: {e}")

    cand_file, _ = _candidate_paths(invoice_path)
    cand_file.parent.mkdir(parents=True, exist_ok=True)
    cand_file.write_text(body.content)
    return {"saved": True}


@router.post("/api/invoices/{filename}/candidate/approve")
async def approve_candidate(filename: str, body: CandidateContentRequest):
    """Validates the reviewed draft against the extraction schema and promotes it to
    approved ground truth (normalized formatting). The candidate draft is removed."""
    invoice_path = _resolve_invoice(filename)
    try:
        extraction = InvoiceExtraction.model_validate_json(body.content)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"Draft failed schema validation: {e}")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Draft is not valid JSON: {e}")

    ground_truth_dir = Path(settings.ground_truth_dir).resolve()
    ground_truth_dir.mkdir(parents=True, exist_ok=True)
    gt_file = ground_truth_dir / f"{invoice_path.stem}.json"
    gt_file.write_text(extraction.model_dump_json(indent=2))

    cand_file, meta_file = _candidate_paths(invoice_path)
    cand_file.unlink(missing_ok=True)
    meta_file.unlink(missing_ok=True)
    return {"approved": True, "ground_truth_filename": gt_file.name}


@router.delete("/api/invoices/{filename}/candidate")
async def discard_candidate(filename: str):
    invoice_path = _resolve_invoice(filename)
    cand_file, meta_file = _candidate_paths(invoice_path)
    if not cand_file.exists():
        raise HTTPException(status_code=404, detail="No candidate ground truth for this invoice")
    cand_file.unlink()
    meta_file.unlink(missing_ok=True)
    return {"discarded": True}

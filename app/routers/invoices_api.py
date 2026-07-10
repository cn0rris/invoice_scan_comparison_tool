from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.utils.files import INVOICE_EXTENSIONS, describe_invoices

router = APIRouter()

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


@router.get("/api/invoices")
async def get_invoices():
    invoice_dir = Path(settings.invoice_dir).resolve()
    ground_truth_dir = Path(settings.ground_truth_dir).resolve()
    return describe_invoices(invoice_dir, ground_truth_dir)


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

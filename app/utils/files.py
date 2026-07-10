from datetime import datetime, timezone
from pathlib import Path

INVOICE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def list_invoices(invoice_dir: Path) -> list[Path]:
    if not invoice_dir.exists():
        return []
    return sorted(
        p for p in invoice_dir.iterdir() if p.is_file() and p.suffix.lower() in INVOICE_EXTENSIONS
    )


def load_ground_truth_text(invoice_path: Path, ground_truth_dir: Path) -> str | None:
    """Returns the raw text of the matching ground-truth file, or None if absent.
    Not validated here — the caller validates against InvoiceExtraction and handles
    malformed files as a per-invoice error rather than a crash."""
    gt_path = ground_truth_dir / f"{invoice_path.stem}.json"
    if not gt_path.exists():
        return None
    return gt_path.read_text()


def candidate_path(invoice_path: Path, candidate_dir: Path) -> Path:
    return candidate_dir / f"{invoice_path.stem}.json"


def candidate_meta_path(invoice_path: Path, candidate_dir: Path) -> Path:
    return candidate_dir / f"{invoice_path.stem}.meta.json"


def ground_truth_status(invoice_path: Path, ground_truth_dir: Path, candidate_dir: Path | None = None) -> str:
    """One of 'valid' | 'invalid' | 'candidate' | 'missing' — used for display on the
    invoices page. An approved ground-truth file always wins; 'candidate' means no
    approved file exists yet but a draft is awaiting review."""
    from app.models.invoice import InvoiceExtraction  # local import: avoids a module-load cycle

    gt_text = load_ground_truth_text(invoice_path, ground_truth_dir)
    if gt_text is None:
        if candidate_dir is not None and candidate_path(invoice_path, candidate_dir).exists():
            return "candidate"
        return "missing"
    try:
        InvoiceExtraction.model_validate_json(gt_text)
    except Exception:  # noqa: BLE001 - any malformed/schema-mismatched GT file is just "invalid" for display
        return "invalid"
    return "valid"


def describe_invoices(invoice_dir: Path, ground_truth_dir: Path, candidate_dir: Path | None = None) -> list[dict]:
    invoices = []
    for path in list_invoices(invoice_dir):
        stat = path.stat()
        invoices.append(
            {
                "filename": path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "ground_truth_status": ground_truth_status(path, ground_truth_dir, candidate_dir),
                "ground_truth_filename": f"{path.stem}.json",
            }
        )
    return invoices

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

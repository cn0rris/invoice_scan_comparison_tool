"""One-off generator for synthetic demo invoices + matching ground truth.

Run manually (`python scripts/generate_sample_data.py`) whenever the sample
data needs regenerating. Not part of the runtime app; not in requirements.txt
(uses reportlab + Pillow, and only Pillow is a runtime dependency).
"""

import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
INVOICE_DIR = ROOT / "data" / "invoices"
GT_DIR = ROOT / "data" / "ground_truth"

sys.path.insert(0, str(ROOT))
from app.models.invoice import InvoiceExtraction  # noqa: E402


INVOICES = {
    "sample_001": {
        "print_date": "January 15, 2024",
        "data": {
            "invoice_number": "INV-1001",
            "invoice_date": "2024-01-15",
            "vendor_name": "Harrison & Cole LLP",
            "client_name": "Acme Corp",
            "matter_number": "M-2024-0042",
            "line_items": [
                {"description": "Legal research re: contract dispute", "hours": 3.5, "rate": 250.0, "amount": 875.0},
                {"description": "Draft settlement letter", "hours": 1.0, "rate": 250.0, "amount": 250.0},
            ],
            "subtotal": 1125.0,
            "tax": 0.0,
            "total": 1125.0,
            "currency": "USD",
        },
    },
    "sample_002": {
        "print_date": "03/22/2024",
        "data": {
            "invoice_number": "INV-1002",
            "invoice_date": "2024-03-22",
            "vendor_name": "Bright & Fields LLP",
            "client_name": "Globex Industries",
            "matter_number": "M-2024-0099",
            "line_items": [
                {"description": "Review merger documents", "hours": 5.0, "rate": 300.0, "amount": 1500.0},
                {"description": "Client meeting re: due diligence", "hours": 2.0, "rate": 300.0, "amount": 600.0},
                {"description": "Deposition prep (flat fee)", "hours": None, "rate": None, "amount": 950.0},
            ],
            "subtotal": 3050.0,
            "tax": 244.0,
            "total": 3294.0,
            "currency": "USD",
        },
    },
    "sample_003": {
        "print_date": "February 10, 2024",
        "data": {
            "invoice_number": "INV-1003",
            "invoice_date": "2024-02-10",
            "vendor_name": "Whitfield Legal Group",
            "client_name": "Initech LLC",
            "matter_number": None,
            "line_items": [
                {"description": "Contract drafting", "hours": 4.0, "rate": 275.0, "amount": 1100.0},
            ],
            "subtotal": 1100.0,
            "tax": 0.0,
            "total": 1100.0,
            "currency": "USD",
        },
    },
}


def render_lines(entry: dict) -> list[str]:
    d = entry["data"]
    lines = [
        f"INVOICE {d['invoice_number']}",
        f"Date: {entry['print_date']}",
        "",
        f"From: {d['vendor_name']}",
        f"Bill To: {d['client_name']}",
    ]
    if d["matter_number"]:
        lines.append(f"Matter No.: {d['matter_number']}")
    lines += ["", "Line Items:"]
    for li in d["line_items"]:
        hours = f"{li['hours']}" if li["hours"] is not None else "-"
        rate = f"${li['rate']:.2f}" if li["rate"] is not None else "-"
        lines.append(f"  - {li['description']} | hours: {hours} | rate: {rate} | amount: ${li['amount']:.2f}")
    lines += [
        "",
        f"Subtotal: ${d['subtotal']:.2f}",
        f"Tax: ${d['tax']:.2f}",
        f"TOTAL DUE: ${d['total']:.2f} {d['currency']}",
    ]
    return lines


def write_pdf(name: str, entry: dict) -> None:
    path = INVOICE_DIR / f"{name}.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    text = c.beginText(72, 720)
    text.setFont("Helvetica", 11)
    for line in render_lines(entry):
        text.textLine(line)
    c.drawText(text)
    c.save()
    print(f"wrote {path}")


def write_png(name: str, entry: dict) -> None:
    path = INVOICE_DIR / f"{name}.png"
    img = Image.new("RGB", (850, 1100), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    y = 60
    for line in render_lines(entry):
        draw.text((60, y), line, fill="black", font=font)
        y += 28
    img.save(path)
    print(f"wrote {path}")


def write_ground_truth(name: str, entry: dict) -> None:
    validated = InvoiceExtraction.model_validate(entry["data"])
    path = GT_DIR / f"{name}.json"
    path.write_text(json.dumps(validated.model_dump(mode="json"), indent=2) + "\n")
    print(f"wrote {path}")


def main() -> None:
    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)

    write_pdf("sample_001", INVOICES["sample_001"])
    write_pdf("sample_002", INVOICES["sample_002"])
    write_png("sample_003", INVOICES["sample_003"])

    for name, entry in INVOICES.items():
        write_ground_truth(name, entry)


if __name__ == "__main__":
    main()

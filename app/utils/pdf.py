import io
from pathlib import Path

from pdf2image import convert_from_path


def rasterize_pdf(pdf_path: Path) -> list[bytes]:
    """Rasterize a PDF into one PNG byte-string per page. Used only for the Ollama
    provider path — Claude accepts PDFs natively and never needs this."""
    images = convert_from_path(str(pdf_path))
    pages: list[bytes] = []
    for image in images:
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        pages.append(buf.getvalue())
    return pages

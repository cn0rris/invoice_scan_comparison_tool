import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.config import settings
from app.routers import invoices_api


def upload_file(filename: str, content: bytes = b"fake-bytes") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


async def test_get_invoices_reports_ground_truth_status(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    gt_dir = tmp_path / "ground_truth"
    invoice_dir.mkdir()
    gt_dir.mkdir()
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))
    monkeypatch.setattr(settings, "ground_truth_dir", str(gt_dir))

    (invoice_dir / "has_valid_gt.pdf").write_bytes(b"pdf")
    (gt_dir / "has_valid_gt.json").write_text(json.dumps({"invoice_number": "INV-1"}))

    (invoice_dir / "has_invalid_gt.pdf").write_bytes(b"pdf")
    (gt_dir / "has_invalid_gt.json").write_text("not valid json")

    (invoice_dir / "no_gt.pdf").write_bytes(b"pdf")

    result = {r["filename"]: r for r in await invoices_api.get_invoices()}
    assert result["has_valid_gt.pdf"]["ground_truth_status"] == "valid"
    assert result["has_invalid_gt.pdf"]["ground_truth_status"] == "invalid"
    assert result["no_gt.pdf"]["ground_truth_status"] == "missing"


async def test_upload_saves_valid_files(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))

    result = await invoices_api.upload_invoices(files=[upload_file("new_invoice.pdf")])

    assert result["saved"] == ["new_invoice.pdf"]
    assert result["skipped"] == []
    assert (invoice_dir / "new_invoice.pdf").read_bytes() == b"fake-bytes"


async def test_upload_rejects_unsupported_extension(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))

    result = await invoices_api.upload_invoices(files=[upload_file("malware.exe")])

    assert result["saved"] == []
    assert result["skipped"][0]["filename"] == "malware.exe"
    assert not (invoice_dir / "malware.exe").exists()


async def test_upload_rejects_filename_collision(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    invoice_dir.mkdir()
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))
    (invoice_dir / "existing.pdf").write_bytes(b"original")

    result = await invoices_api.upload_invoices(files=[upload_file("existing.pdf", b"overwrite-attempt")])

    assert result["saved"] == []
    assert result["skipped"][0]["filename"] == "existing.pdf"
    assert (invoice_dir / "existing.pdf").read_bytes() == b"original"  # not clobbered


async def test_upload_strips_path_components_from_filename(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))

    result = await invoices_api.upload_invoices(files=[upload_file("../../etc/evil.pdf")])

    assert result["saved"] == ["evil.pdf"]
    assert (invoice_dir / "evil.pdf").exists()
    assert not (tmp_path / "etc").exists()


async def test_get_invoice_file_returns_the_file(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    invoice_dir.mkdir()
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))
    (invoice_dir / "sample.pdf").write_bytes(b"%PDF-1.4 content")

    response = await invoices_api.get_invoice_file("sample.pdf")

    assert response.path == invoice_dir / "sample.pdf"
    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="sample.pdf"'


async def test_get_invoice_file_404_when_missing(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    invoice_dir.mkdir()
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.get_invoice_file("does_not_exist.pdf")
    assert exc_info.value.status_code == 404


async def test_get_invoice_file_rejects_path_traversal(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    invoice_dir.mkdir()
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))
    outside_secret = tmp_path / "secret.txt"
    outside_secret.write_text("do not serve me")

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.get_invoice_file("../secret.txt")
    assert exc_info.value.status_code == 404


async def test_get_invoice_file_rejects_disallowed_extension(tmp_path: Path, monkeypatch):
    invoice_dir = tmp_path / "invoices"
    invoice_dir.mkdir()
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))
    (invoice_dir / "notes.txt").write_text("not an invoice")

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.get_invoice_file("notes.txt")
    assert exc_info.value.status_code == 404

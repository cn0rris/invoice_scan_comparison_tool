import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.config import settings
from app.providers.base import ExtractionResult
from app.routers import invoices_api


def upload_file(filename: str, content: bytes = b"fake-bytes") -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename)


class FakeProvider:
    def __init__(self, result: ExtractionResult):
        self._result = result
        self.calls: list[tuple[Path, str]] = []

    async def extract(self, invoice_path: Path, prompt: str) -> ExtractionResult:
        self.calls.append((invoice_path, prompt))
        return self._result


@pytest.fixture
def candidate_env(tmp_path: Path, monkeypatch):
    """Invoice/GT/candidate dirs wired into settings, with one GT-less invoice present."""
    invoice_dir = tmp_path / "invoices"
    gt_dir = tmp_path / "ground_truth"
    cand_dir = tmp_path / "ground_truth_candidates"
    invoice_dir.mkdir()
    gt_dir.mkdir()
    monkeypatch.setattr(settings, "invoice_dir", str(invoice_dir))
    monkeypatch.setattr(settings, "ground_truth_dir", str(gt_dir))
    monkeypatch.setattr(settings, "ground_truth_candidate_dir", str(cand_dir))
    (invoice_dir / "new_invoice.pdf").write_bytes(b"pdf")
    return {"invoice_dir": invoice_dir, "gt_dir": gt_dir, "cand_dir": cand_dir}


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
    assert result["has_valid_gt.pdf"]["ground_truth_filename"] == "has_valid_gt.json"


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


async def test_get_ground_truth_file_returns_the_file(tmp_path: Path, monkeypatch):
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir()
    monkeypatch.setattr(settings, "ground_truth_dir", str(gt_dir))
    (gt_dir / "sample.json").write_text(json.dumps({"invoice_number": "INV-1"}))

    response = await invoices_api.get_ground_truth_file("sample.json")

    assert response.path == gt_dir / "sample.json"
    assert response.media_type == "application/json"
    assert response.headers["content-disposition"] == 'inline; filename="sample.json"'


async def test_get_ground_truth_file_404_when_missing(tmp_path: Path, monkeypatch):
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir()
    monkeypatch.setattr(settings, "ground_truth_dir", str(gt_dir))

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.get_ground_truth_file("does_not_exist.json")
    assert exc_info.value.status_code == 404


async def test_get_ground_truth_file_rejects_path_traversal(tmp_path: Path, monkeypatch):
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir()
    monkeypatch.setattr(settings, "ground_truth_dir", str(gt_dir))
    (tmp_path / "secret.json").write_text("do not serve me")

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.get_ground_truth_file("../secret.json")
    assert exc_info.value.status_code == 404


async def test_get_ground_truth_file_rejects_non_json(tmp_path: Path, monkeypatch):
    gt_dir = tmp_path / "ground_truth"
    gt_dir.mkdir()
    monkeypatch.setattr(settings, "ground_truth_dir", str(gt_dir))
    (gt_dir / "sample.txt").write_text("not json")

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.get_ground_truth_file("sample.txt")
    assert exc_info.value.status_code == 404


async def test_invoice_with_candidate_reports_candidate_status(candidate_env):
    candidate_env["cand_dir"].mkdir()
    (candidate_env["cand_dir"] / "new_invoice.json").write_text(json.dumps({"invoice_number": "INV-9"}))

    result = {r["filename"]: r for r in await invoices_api.get_invoices()}
    assert result["new_invoice.pdf"]["ground_truth_status"] == "candidate"


async def test_generate_candidate_writes_draft_and_meta(candidate_env, monkeypatch):
    fake = FakeProvider(
        ExtractionResult(raw_text="{}", parsed={"invoice_number": "INV-9", "total": 100.0}, duration_ms=42)
    )
    monkeypatch.setattr(invoices_api, "get_provider", lambda model_id: fake)

    result = await invoices_api.generate_candidate(
        "new_invoice.pdf", invoices_api.GenerateCandidateRequest(model_id="claude-opus-4-8")
    )

    cand_file = candidate_env["cand_dir"] / "new_invoice.json"
    meta_file = candidate_env["cand_dir"] / "new_invoice.meta.json"
    assert json.loads(cand_file.read_text())["invoice_number"] == "INV-9"
    meta = json.loads(meta_file.read_text())
    assert meta["model_id"] == "claude-opus-4-8"
    assert result["meta"]["duration_ms"] == 42
    assert fake.calls[0][0] == candidate_env["invoice_dir"] / "new_invoice.pdf"


async def test_generate_candidate_409_when_ground_truth_exists(candidate_env, monkeypatch):
    (candidate_env["gt_dir"] / "new_invoice.json").write_text(json.dumps({"invoice_number": "INV-1"}))
    monkeypatch.setattr(
        invoices_api, "get_provider", lambda model_id: pytest.fail("provider must not be called")
    )

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.generate_candidate(
            "new_invoice.pdf", invoices_api.GenerateCandidateRequest(model_id="claude-opus-4-8")
        )
    assert exc_info.value.status_code == 409


async def test_generate_candidate_502_on_extraction_failure(candidate_env, monkeypatch):
    fake = FakeProvider(ExtractionResult(raw_text="", parsed=None, error="model exploded", duration_ms=5))
    monkeypatch.setattr(invoices_api, "get_provider", lambda model_id: fake)

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.generate_candidate(
            "new_invoice.pdf", invoices_api.GenerateCandidateRequest(model_id="some-model")
        )
    assert exc_info.value.status_code == 502
    assert not (candidate_env["cand_dir"] / "new_invoice.json").exists()


async def test_save_candidate_accepts_json_and_rejects_syntax_errors(candidate_env):
    await invoices_api.save_candidate(
        "new_invoice.pdf", invoices_api.CandidateContentRequest(content='{"invoice_number": "edited"}')
    )
    assert json.loads((candidate_env["cand_dir"] / "new_invoice.json").read_text())["invoice_number"] == "edited"

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.save_candidate(
            "new_invoice.pdf", invoices_api.CandidateContentRequest(content="{not json")
        )
    assert exc_info.value.status_code == 422


async def test_approve_candidate_promotes_to_ground_truth(candidate_env):
    candidate_env["cand_dir"].mkdir()
    (candidate_env["cand_dir"] / "new_invoice.json").write_text("{}")
    (candidate_env["cand_dir"] / "new_invoice.meta.json").write_text("{}")

    result = await invoices_api.approve_candidate(
        "new_invoice.pdf",
        invoices_api.CandidateContentRequest(content=json.dumps({"invoice_number": "INV-9", "total": 100.0})),
    )

    assert result["approved"] is True
    gt = json.loads((candidate_env["gt_dir"] / "new_invoice.json").read_text())
    assert gt["invoice_number"] == "INV-9"
    assert gt["total"] == 100.0
    assert not (candidate_env["cand_dir"] / "new_invoice.json").exists()
    assert not (candidate_env["cand_dir"] / "new_invoice.meta.json").exists()


async def test_approve_candidate_422_on_schema_violation(candidate_env):
    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.approve_candidate(
            "new_invoice.pdf",
            invoices_api.CandidateContentRequest(content=json.dumps({"total": "not-a-number"})),
        )
    assert exc_info.value.status_code == 422
    assert not (candidate_env["gt_dir"] / "new_invoice.json").exists()


async def test_discard_candidate_removes_files(candidate_env):
    candidate_env["cand_dir"].mkdir()
    (candidate_env["cand_dir"] / "new_invoice.json").write_text("{}")
    (candidate_env["cand_dir"] / "new_invoice.meta.json").write_text("{}")

    result = await invoices_api.discard_candidate("new_invoice.pdf")

    assert result["discarded"] is True
    assert not (candidate_env["cand_dir"] / "new_invoice.json").exists()
    assert not (candidate_env["cand_dir"] / "new_invoice.meta.json").exists()


async def test_get_candidate_returns_content_and_meta(candidate_env):
    candidate_env["cand_dir"].mkdir()
    (candidate_env["cand_dir"] / "new_invoice.json").write_text('{"invoice_number": "INV-9"}')
    (candidate_env["cand_dir"] / "new_invoice.meta.json").write_text('{"model_id": "m"}')

    result = await invoices_api.get_candidate("new_invoice.pdf")
    assert json.loads(result["content"])["invoice_number"] == "INV-9"
    assert result["meta"]["model_id"] == "m"


async def test_candidate_endpoints_404_for_unknown_invoice(candidate_env):
    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.generate_candidate(
            "../evil.pdf", invoices_api.GenerateCandidateRequest(model_id="m")
        )
    assert exc_info.value.status_code == 404

    with pytest.raises(HTTPException) as exc_info:
        await invoices_api.get_candidate("nope.pdf")
    assert exc_info.value.status_code == 404

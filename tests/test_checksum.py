import json
from pathlib import Path

import pytest

from app.orchestrator.checksum import compute_run_checksum


@pytest.fixture
def dirs(tmp_path: Path):
    invoice_dir = tmp_path / "invoices"
    gt_dir = tmp_path / "ground_truth"
    invoice_dir.mkdir()
    gt_dir.mkdir()
    (invoice_dir / "inv_001.pdf").write_bytes(b"pdf-bytes-v1")
    (gt_dir / "inv_001.json").write_text(json.dumps({"invoice_number": "INV-1"}))
    return invoice_dir, gt_dir


@pytest.fixture(autouse=True)
def no_ollama(monkeypatch):
    async def fake_digests():
        return {}

    monkeypatch.setattr("app.orchestrator.checksum.get_ollama_digests", fake_digests)


async def test_checksum_is_deterministic(dirs):
    invoice_dir, gt_dir = dirs
    a = await compute_run_checksum(invoice_dir, gt_dir, "prompt text", ["claude-haiku-4-5"])
    b = await compute_run_checksum(invoice_dir, gt_dir, "prompt text", ["claude-haiku-4-5"])
    assert a == b


async def test_checksum_changes_with_invoice_content(dirs):
    invoice_dir, gt_dir = dirs
    before = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["claude-haiku-4-5"])
    (invoice_dir / "inv_001.pdf").write_bytes(b"pdf-bytes-v2")
    after = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["claude-haiku-4-5"])
    assert before != after


async def test_checksum_changes_with_ground_truth_content(dirs):
    invoice_dir, gt_dir = dirs
    before = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["claude-haiku-4-5"])
    (gt_dir / "inv_001.json").write_text(json.dumps({"invoice_number": "INV-999"}))
    after = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["claude-haiku-4-5"])
    assert before != after


async def test_checksum_changes_with_prompt(dirs):
    invoice_dir, gt_dir = dirs
    a = await compute_run_checksum(invoice_dir, gt_dir, "prompt A", ["claude-haiku-4-5"])
    b = await compute_run_checksum(invoice_dir, gt_dir, "prompt B", ["claude-haiku-4-5"])
    assert a != b


async def test_checksum_changes_with_model_list(dirs):
    invoice_dir, gt_dir = dirs
    a = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["claude-haiku-4-5"])
    b = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["claude-haiku-4-5", "claude-sonnet-5"])
    assert a != b


async def test_checksum_ignores_model_order(dirs):
    invoice_dir, gt_dir = dirs
    a = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["claude-haiku-4-5", "claude-sonnet-5"])
    b = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["claude-sonnet-5", "claude-haiku-4-5"])
    assert a == b


async def test_checksum_incorporates_ollama_digest(dirs, monkeypatch):
    invoice_dir, gt_dir = dirs

    async def digests_v1():
        return {"llava": "sha256:v1"}

    async def digests_v2():
        return {"llava": "sha256:v2"}

    monkeypatch.setattr("app.orchestrator.checksum.get_ollama_digests", digests_v1)
    a = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["llava"])

    monkeypatch.setattr("app.orchestrator.checksum.get_ollama_digests", digests_v2)
    b = await compute_run_checksum(invoice_dir, gt_dir, "prompt", ["llava"])

    assert a != b

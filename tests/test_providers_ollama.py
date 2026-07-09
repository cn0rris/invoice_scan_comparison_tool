import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.providers.ollama_provider import OllamaProvider

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True, scope="session")
def fixtures_dir():
    FIXTURES.mkdir(exist_ok=True)
    (FIXTURES / "sample.pdf").write_bytes(b"%PDF-1.4 fake pdf content")
    (FIXTURES / "sample.png").write_bytes(b"\x89PNG\r\n\x1a\nfake png content")
    yield


def make_provider() -> OllamaProvider:
    return OllamaProvider("llava", base_url="http://localhost:11434", timeout_s=10.0)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://localhost:11434/api/chat")
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._json_data


def install_fake_client(monkeypatch, post_impl):
    fake_client = MagicMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(side_effect=post_impl)
    monkeypatch.setattr("app.providers.ollama_provider.httpx.AsyncClient", MagicMock(return_value=fake_client))
    return fake_client


async def test_png_sends_single_image_and_json_schema_format(monkeypatch):
    provider = make_provider()
    captured = {}

    async def post_impl(url, json):
        captured.update(json)
        return FakeResponse(json_data={"message": {"content": json_dump_invoice()}})

    install_fake_client(monkeypatch, post_impl)
    result = await provider.extract(FIXTURES / "sample.png", "extract this")

    assert len(captured["messages"][0]["images"]) == 1
    assert "properties" in captured["format"]  # a JSON schema, not the literal string "json"
    assert result.parsed["invoice_number"] == "INV-1"


async def test_pdf_rasterizes_each_page(monkeypatch):
    provider = make_provider()
    monkeypatch.setattr(
        "app.providers.ollama_provider.rasterize_pdf", lambda path: [b"page1-bytes", b"page2-bytes"]
    )
    captured = {}

    async def post_impl(url, json):
        captured.update(json)
        return FakeResponse(json_data={"message": {"content": json_dump_invoice()}})

    install_fake_client(monkeypatch, post_impl)
    await provider.extract(FIXTURES / "sample.pdf", "extract this")

    assert len(captured["messages"][0]["images"]) == 2


async def test_fallback_regex_extraction_when_not_pure_json(monkeypatch):
    provider = make_provider()

    async def post_impl(url, json):
        content = "Here you go:\n" + json_dump_invoice() + "\nHope that helps!"
        return FakeResponse(json_data={"message": {"content": content}})

    install_fake_client(monkeypatch, post_impl)
    result = await provider.extract(FIXTURES / "sample.png", "extract this")
    assert result.parsed["invoice_number"] == "INV-1"


async def test_unparseable_output_is_parse_failure(monkeypatch):
    provider = make_provider()

    async def post_impl(url, json):
        return FakeResponse(json_data={"message": {"content": "not json at all"}})

    install_fake_client(monkeypatch, post_impl)
    result = await provider.extract(FIXTURES / "sample.png", "extract this")
    assert result.parsed is None
    assert result.error is not None


async def test_connect_error_mapped(monkeypatch):
    provider = make_provider()

    async def post_impl(url, json):
        raise httpx.ConnectError("refused")

    install_fake_client(monkeypatch, post_impl)
    result = await provider.extract(FIXTURES / "sample.png", "extract this")
    assert "is it running natively on the host" in result.error


async def test_timeout_mapped(monkeypatch):
    provider = make_provider()

    async def post_impl(url, json):
        raise httpx.TimeoutException("timed out")

    install_fake_client(monkeypatch, post_impl)
    result = await provider.extract(FIXTURES / "sample.png", "extract this")
    assert "timed out" in result.error


async def test_http_status_error_mapped(monkeypatch):
    provider = make_provider()

    async def post_impl(url, json):
        return FakeResponse(status_code=500, text="internal error")

    install_fake_client(monkeypatch, post_impl)
    result = await provider.extract(FIXTURES / "sample.png", "extract this")
    assert "500" in result.error


def json_dump_invoice() -> str:
    return json.dumps(
        {
            "invoice_number": "INV-1",
            "invoice_date": "2024-01-15",
            "vendor_name": "Test Vendor",
            "client_name": "Test Client",
            "matter_number": None,
            "line_items": [],
            "subtotal": 0,
            "tax": 0,
            "total": 0,
            "currency": "USD",
        }
    )

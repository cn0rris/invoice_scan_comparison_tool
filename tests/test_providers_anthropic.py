from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import anthropic
import httpx
import pytest

from app.models.invoice import InvoiceExtraction
from app.providers.anthropic_provider import AnthropicProvider

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True, scope="session")
def fixtures_dir():
    FIXTURES.mkdir(exist_ok=True)
    (FIXTURES / "sample.pdf").write_bytes(b"%PDF-1.4 fake pdf content")
    (FIXTURES / "sample.png").write_bytes(b"\x89PNG\r\n\x1a\nfake png content")
    yield


def make_provider(model_id: str) -> AnthropicProvider:
    provider = AnthropicProvider(model_id, api_key="test-key", timeout_s=10.0)
    return provider


def fake_response(stop_reason: str, parsed_output=None, content=None):
    resp = MagicMock()
    resp.stop_reason = stop_reason
    resp.parsed_output = parsed_output
    resp.content = content or []
    return resp


async def test_pdf_builds_document_block(monkeypatch):
    provider = make_provider("claude-sonnet-5")
    captured = {}

    async def fake_parse(**kwargs):
        captured.update(kwargs)
        return fake_response("end_turn", parsed_output=InvoiceExtraction(invoice_number="INV-1"))

    provider._client.with_options = MagicMock(return_value=MagicMock(messages=MagicMock(parse=AsyncMock(side_effect=fake_parse))))

    result = await provider.extract(FIXTURES / "sample.pdf", "extract this")
    block = captured["messages"][0]["content"][0]
    assert block["type"] == "document"
    assert block["source"]["media_type"] == "application/pdf"
    assert result.parsed["invoice_number"] == "INV-1"


async def test_png_builds_image_block(monkeypatch):
    provider = make_provider("claude-sonnet-5")
    captured = {}

    async def fake_parse(**kwargs):
        captured.update(kwargs)
        return fake_response("end_turn", parsed_output=InvoiceExtraction())

    provider._client.with_options = MagicMock(return_value=MagicMock(messages=MagicMock(parse=AsyncMock(side_effect=fake_parse))))

    await provider.extract(FIXTURES / "sample.png", "extract this")
    block = captured["messages"][0]["content"][0]
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"


@pytest.mark.parametrize(
    "model_id,expects_thinking_key,expected_value",
    [
        ("claude-opus-4-8", True, {"type": "disabled"}),
        ("claude-sonnet-5", True, {"type": "disabled"}),
        ("claude-haiku-4-5", False, None),
    ],
)
async def test_thinking_config_is_per_model(monkeypatch, model_id, expects_thinking_key, expected_value):
    provider = make_provider(model_id)
    captured = {}

    async def fake_parse(**kwargs):
        captured.update(kwargs)
        return fake_response("end_turn", parsed_output=InvoiceExtraction())

    provider._client.with_options = MagicMock(return_value=MagicMock(messages=MagicMock(parse=AsyncMock(side_effect=fake_parse))))

    await provider.extract(FIXTURES / "sample.pdf", "extract this")
    if expects_thinking_key:
        assert captured["thinking"] == expected_value
    else:
        assert "thinking" not in captured


async def test_refusal_sets_error():
    provider = make_provider("claude-sonnet-5")

    async def fake_parse(**kwargs):
        return fake_response("refusal", parsed_output=None)

    provider._client.with_options = MagicMock(return_value=MagicMock(messages=MagicMock(parse=AsyncMock(side_effect=fake_parse))))

    result = await provider.extract(FIXTURES / "sample.pdf", "extract this")
    assert result.error is not None
    assert "refusal" in result.error.lower()


async def test_rate_limit_error_mapped():
    provider = make_provider("claude-sonnet-5")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request)

    async def fake_parse(**kwargs):
        raise anthropic.RateLimitError("rate limited", response=response, body=None)

    provider._client.with_options = MagicMock(return_value=MagicMock(messages=MagicMock(parse=AsyncMock(side_effect=fake_parse))))

    result = await provider.extract(FIXTURES / "sample.pdf", "extract this")
    assert result.error is not None
    assert "rate limited" in result.error.lower()


async def test_connection_error_mapped():
    provider = make_provider("claude-sonnet-5")
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    async def fake_parse(**kwargs):
        raise anthropic.APIConnectionError(request=request)

    provider._client.with_options = MagicMock(return_value=MagicMock(messages=MagicMock(parse=AsyncMock(side_effect=fake_parse))))

    result = await provider.extract(FIXTURES / "sample.pdf", "extract this")
    assert result.error is not None
    assert "connection error" in result.error.lower()


async def test_unexpected_exception_never_raises():
    provider = make_provider("claude-sonnet-5")

    async def fake_parse(**kwargs):
        raise ValueError("boom")

    provider._client.with_options = MagicMock(return_value=MagicMock(messages=MagicMock(parse=AsyncMock(side_effect=fake_parse))))

    result = await provider.extract(FIXTURES / "sample.pdf", "extract this")
    assert result.error is not None
    assert "unexpected error" in result.error.lower()

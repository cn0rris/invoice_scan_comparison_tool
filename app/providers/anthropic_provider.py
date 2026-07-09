import base64
import time
from pathlib import Path

import anthropic

from app.providers.base import BaseProvider, ExtractionResult
from app.models.invoice import InvoiceExtraction

# Models whose thinking config accepts an explicit {"type": "disabled"} value.
# Older-tier models (e.g. claude-haiku-4-5) use a different thinking paradigm
# and should simply have `thinking` omitted rather than sent "disabled".
_MODELS_ACCEPTING_DISABLED_THINKING = {"claude-opus-4-8", "claude-sonnet-5"}

_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class AnthropicProvider(BaseProvider):
    kind = "anthropic"

    def __init__(self, model_id: str, api_key: str, timeout_s: float):
        self.model_id = model_id
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._timeout_s = timeout_s

    def _build_document_block(self, invoice_path: Path) -> dict:
        data = base64.standard_b64encode(invoice_path.read_bytes()).decode("ascii")
        suffix = invoice_path.suffix.lower()
        if suffix == ".pdf":
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": data},
            }
        media_type = _IMAGE_MEDIA_TYPES.get(suffix, "image/png")
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}

    async def extract(self, invoice_path: Path, prompt: str) -> ExtractionResult:
        started = time.monotonic()
        document_block = self._build_document_block(invoice_path)
        kwargs: dict = {}
        if self.model_id in _MODELS_ACCEPTING_DISABLED_THINKING:
            kwargs["thinking"] = {"type": "disabled"}
        try:
            client = self._client.with_options(timeout=self._timeout_s)
            response = await client.messages.parse(
                model=self.model_id,
                max_tokens=4096,
                system=[{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[
                    {
                        "role": "user",
                        "content": [document_block, {"type": "text", "text": "Extract the invoice data now."}],
                    }
                ],
                output_format=InvoiceExtraction,
                **kwargs,
            )
        except anthropic.RateLimitError as e:
            return ExtractionResult(raw_text="", error=f"Rate limited: {e}", duration_ms=_elapsed_ms(started))
        except anthropic.APIConnectionError as e:
            return ExtractionResult(
                raw_text="", error=f"Connection error to Anthropic API: {e}", duration_ms=_elapsed_ms(started)
            )
        except anthropic.APIStatusError as e:
            return ExtractionResult(
                raw_text="", error=f"Anthropic API error ({e.status_code}): {e.message}", duration_ms=_elapsed_ms(started)
            )
        except Exception as e:  # noqa: BLE001 - last-resort net, one pair failing must not abort the run
            return ExtractionResult(raw_text="", error=f"Unexpected error: {e}", duration_ms=_elapsed_ms(started))

        duration_ms = _elapsed_ms(started)
        if response.stop_reason == "refusal":
            return ExtractionResult(
                raw_text="", error="Model refused the request (stop_reason=refusal)", duration_ms=duration_ms
            )
        if response.parsed_output is None:
            raw_text = "".join(b.text for b in response.content if b.type == "text")
            return ExtractionResult(
                raw_text=raw_text,
                error=f"Model output did not parse against the schema (stop_reason={response.stop_reason})",
                duration_ms=duration_ms,
            )
        return ExtractionResult(
            raw_text=response.parsed_output.model_dump_json(),
            parsed=response.parsed_output.model_dump(mode="json"),
            duration_ms=duration_ms,
        )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)

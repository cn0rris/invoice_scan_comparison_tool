import base64
import json
import re
import time
from pathlib import Path

import httpx

from app.providers.base import BaseProvider, ExtractionResult
from app.models.invoice import InvoiceExtraction
from app.utils.pdf import rasterize_pdf

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class OllamaProvider(BaseProvider):
    kind = "ollama"

    def __init__(self, model_id: str, base_url: str, timeout_s: float):
        self.model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def _build_images(self, invoice_path: Path) -> list[str]:
        if invoice_path.suffix.lower() == ".pdf":
            pages = rasterize_pdf(invoice_path)
        else:
            pages = [invoice_path.read_bytes()]
        return [base64.standard_b64encode(page).decode("ascii") for page in pages]

    def _extract_json(self, raw_text: str) -> dict | None:
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass
        match = _JSON_BLOCK_RE.search(raw_text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return None

    async def extract(self, invoice_path: Path, prompt: str) -> ExtractionResult:
        started = time.monotonic()
        try:
            images = self._build_images(invoice_path)
        except Exception as e:  # noqa: BLE001 - e.g. missing poppler/pdf2image failure
            return ExtractionResult(raw_text="", error=f"Failed to prepare invoice image(s): {e}", duration_ms=_elapsed_ms(started))

        payload = {
            "model": self.model_id,
            "stream": False,
            "format": InvoiceExtraction.model_json_schema(),
            "messages": [{"role": "user", "content": prompt, "images": images}],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(f"{self._base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError:
            return ExtractionResult(
                raw_text="",
                error=f"Could not reach Ollama at {self._base_url} — is it running natively on the host?",
                duration_ms=_elapsed_ms(started),
            )
        except httpx.TimeoutException:
            return ExtractionResult(
                raw_text="", error=f"Ollama request timed out after {self._timeout_s}s", duration_ms=_elapsed_ms(started)
            )
        except httpx.HTTPStatusError as e:
            return ExtractionResult(
                raw_text="", error=f"Ollama returned HTTP {e.response.status_code}: {e.response.text[:500]}",
                duration_ms=_elapsed_ms(started),
            )
        except Exception as e:  # noqa: BLE001 - last-resort net, one pair failing must not abort the run
            return ExtractionResult(raw_text="", error=f"Unexpected error: {e}", duration_ms=_elapsed_ms(started))

        raw_text = data.get("message", {}).get("content", "")
        parsed = self._extract_json(raw_text)
        duration_ms = _elapsed_ms(started)
        if parsed is None:
            return ExtractionResult(raw_text=raw_text, error="Failed to parse model output as JSON", duration_ms=duration_ms)
        return ExtractionResult(raw_text=raw_text, parsed=parsed, duration_ms=duration_ms)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)

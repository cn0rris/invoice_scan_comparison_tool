from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel


class ExtractionResult(BaseModel):
    raw_text: str
    parsed: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: int


class BaseProvider(ABC):
    kind: str  # "anthropic" | "ollama" — selects which concurrency semaphore to use

    @abstractmethod
    async def extract(self, invoice_path: Path, prompt: str) -> ExtractionResult: ...

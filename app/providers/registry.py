import httpx

from app.config import settings
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import BaseProvider
from app.providers.ollama_provider import OllamaProvider

ANTHROPIC_MODELS = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]
# To add another Claude model later, just append its ID here.


async def list_ollama_models() -> dict:
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_tags_timeout_s) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
        models = sorted(m["name"] for m in data.get("models", []))
        return {"available": True, "models": models}
    except Exception as e:  # noqa: BLE001 - Ollama being unreachable is an expected, not exceptional, state
        return {
            "available": False,
            "models": [],
            "error": f"Could not reach Ollama at {settings.ollama_base_url} — is it running natively on the host? ({e})",
        }


def get_provider(model_id: str) -> BaseProvider:
    if model_id in ANTHROPIC_MODELS:
        return AnthropicProvider(model_id, settings.anthropic_api_key, settings.anthropic_timeout_s)
    return OllamaProvider(model_id, settings.ollama_base_url, settings.ollama_timeout_s)


def provider_kind(model_id: str) -> str:
    return "anthropic" if model_id in ANTHROPIC_MODELS else "ollama"

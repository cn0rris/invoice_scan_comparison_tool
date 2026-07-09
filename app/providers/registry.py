import httpx

from app.config import settings
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import BaseProvider
from app.providers.ollama_provider import OllamaProvider

ANTHROPIC_MODELS = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]
# To add another Claude model later, just append its ID here.


async def _fetch_ollama_tags_raw() -> list[dict]:
    async with httpx.AsyncClient(timeout=settings.ollama_tags_timeout_s) as client:
        response = await client.get(f"{settings.ollama_base_url}/api/tags")
        response.raise_for_status()
        data = response.json()
    return data.get("models", [])


async def list_ollama_models() -> dict:
    try:
        models = sorted(m["name"] for m in await _fetch_ollama_tags_raw())
        return {"available": True, "models": models}
    except Exception as e:  # noqa: BLE001 - Ollama being unreachable is an expected, not exceptional, state
        return {
            "available": False,
            "models": [],
            "error": f"Could not reach Ollama at {settings.ollama_base_url} — is it running natively on the host? ({e})",
        }


async def get_ollama_digests() -> dict[str, str]:
    """Maps Ollama model name -> content digest, used as the model's "version" for
    run checksums (an Ollama model can be silently re-pulled/updated under the same
    name; the digest changes when that happens, the name does not). Returns an empty
    dict if Ollama is unreachable — callers fall back to the bare model name."""
    try:
        raw = await _fetch_ollama_tags_raw()
        return {m["name"]: m.get("digest", "") for m in raw}
    except Exception:  # noqa: BLE001 - Ollama being unreachable is an expected, not exceptional, state
        return {}


def get_provider(model_id: str) -> BaseProvider:
    if model_id in ANTHROPIC_MODELS:
        return AnthropicProvider(model_id, settings.anthropic_api_key, settings.anthropic_timeout_s)
    return OllamaProvider(model_id, settings.ollama_base_url, settings.ollama_timeout_s)


def provider_kind(model_id: str) -> str:
    return "anthropic" if model_id in ANTHROPIC_MODELS else "ollama"

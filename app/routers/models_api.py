from fastapi import APIRouter

from app.providers.registry import ANTHROPIC_MODELS, list_ollama_models

router = APIRouter()


@router.get("/api/models")
async def get_models():
    ollama = await list_ollama_models()
    return {"anthropic": ANTHROPIC_MODELS, "ollama": ollama}

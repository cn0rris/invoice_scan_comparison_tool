import hashlib
from pathlib import Path

from app.providers.registry import ANTHROPIC_MODELS, get_ollama_digests
from app.utils.files import list_invoices, load_ground_truth_text


async def compute_run_checksum(
    invoice_dir: Path, ground_truth_dir: Path, prompt: str, models: list[str]
) -> str:
    """Hashes every "relevant piece" that determines a run's outcome: each invoice
    file's bytes, its matched ground-truth file's bytes (a ground-truth edit should
    invalidate reuse too, since it changes the scored mistake counts even though the
    raw model output would be identical), the exact prompt text, and each selected
    model's identity — including an Ollama model's content digest, since a model can
    be silently re-pulled under the same name. Used to detect "this exact run has
    already been done" so we can prompt before re-running it."""
    ollama_digests = await get_ollama_digests()

    h = hashlib.sha256()
    for invoice_path in list_invoices(invoice_dir):
        h.update(b"|INVOICE|")
        h.update(invoice_path.name.encode())
        h.update(invoice_path.read_bytes())
        gt_text = load_ground_truth_text(invoice_path, ground_truth_dir)
        h.update(b"|GROUND_TRUTH|")
        h.update((gt_text or "").encode())

    h.update(b"|PROMPT|")
    h.update(prompt.encode())

    h.update(b"|MODELS|")
    for model_id in sorted(models):
        version = model_id if model_id in ANTHROPIC_MODELS else ollama_digests.get(model_id, model_id)
        h.update(f"{model_id}:{version}".encode())

    return h.hexdigest()

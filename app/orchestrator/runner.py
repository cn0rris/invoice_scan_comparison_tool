import asyncio
import json
from pathlib import Path
from typing import Optional

from app.config import settings
from app.db import compute_summary, db
from app.diff.engine import diff_invoice
from app.models.invoice import InvoiceExtraction
from app.orchestrator.ws_manager import manager
from app.providers.registry import get_provider, provider_kind
from app.utils.files import list_invoices, load_ground_truth_text

_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_semaphore(kind: str) -> asyncio.Semaphore:
    if kind not in _semaphores:
        limit = settings.anthropic_max_concurrency if kind == "anthropic" else settings.ollama_max_concurrency
        _semaphores[kind] = asyncio.Semaphore(limit)
    return _semaphores[kind]


async def start_run(run_id: str, models: list[str], prompt: str, invoice_dir: Path, ground_truth_dir: Path) -> None:
    invoices = list_invoices(invoice_dir)

    pairs_meta = []
    for invoice_path in invoices:
        gt_text = load_ground_truth_text(invoice_path, ground_truth_dir)
        gt_valid_json: Optional[str] = None
        if gt_text is not None:
            try:
                InvoiceExtraction.model_validate_json(gt_text)
                gt_valid_json = gt_text
            except Exception:  # noqa: BLE001 - a malformed GT file is a per-invoice condition, not a crash
                gt_valid_json = None
        for model_id in models:
            pairs_meta.append(
                {
                    "model_id": model_id,
                    "invoice_stem": invoice_path.stem,
                    "invoice_filename": invoice_path.name,
                    "ground_truth_json": gt_valid_json,
                    "invoice_path": invoice_path,
                }
            )

    db_pairs = [{k: v for k, v in p.items() if k != "invoice_path"} for p in pairs_meta]
    inserted = await db.insert_pending_results(run_id, db_pairs)
    await db.set_run_running(run_id, total_pairs=len(inserted))
    await manager.broadcast(run_id, {"type": "progress", "completed": 0, "total": len(inserted)})

    tasks = []
    for meta, row in zip(pairs_meta, inserted):
        if row["status"] == "no_ground_truth":
            # Nothing to run — no matching (or malformed) ground truth for this invoice.
            await manager.broadcast(
                run_id,
                {
                    "type": "result_update",
                    "result_id": row["id"],
                    "model_id": meta["model_id"],
                    "invoice_stem": meta["invoice_stem"],
                    "status": "no_ground_truth",
                    "mistake_count": None,
                    "error_message": None,
                },
            )
            continue
        tasks.append(
            process_one(run_id, row["id"], meta["model_id"], meta["invoice_stem"], meta["invoice_path"], meta["ground_truth_json"], prompt)
        )

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    results = await db.get_results_for_run(run_id)
    any_success = any(r["status"] == "success" for r in results)
    any_attempted = any(r["status"] != "no_ground_truth" for r in results)
    final_status = "completed" if any_success or not any_attempted else "failed"
    await db.finish_run(run_id, final_status)

    run = await db.get_run(run_id)
    summary = compute_summary(run, results)
    await manager.broadcast(run_id, {"type": "run_complete", "summary": summary})


async def process_one(
    run_id: str,
    result_id: str,
    model_id: str,
    invoice_stem: str,
    invoice_path: Path,
    ground_truth_json: str,
    prompt: str,
) -> None:
    await db.mark_result_running(result_id)
    await manager.broadcast(
        run_id,
        {
            "type": "result_update",
            "result_id": result_id,
            "model_id": model_id,
            "invoice_stem": invoice_stem,
            "status": "running",
        },
    )

    kind = provider_kind(model_id)
    sem = _get_semaphore(kind)
    try:
        provider = get_provider(model_id)
        async with sem:
            extraction = await provider.extract(invoice_path, prompt)
    except Exception as e:  # noqa: BLE001 - a bug in one pair must never kill the whole run
        extraction = None
        unhandled_error = f"Unhandled orchestration error: {e}"
    else:
        unhandled_error = None

    if extraction is None or extraction.error:
        status = "error"
        raw_output = extraction.raw_text if extraction else None
        parsed_json = None
        diff_json = None
        mistake_count = None
        error_message = unhandled_error or (extraction.error if extraction else None)
        duration_ms = extraction.duration_ms if extraction else None
    else:
        expected = InvoiceExtraction.model_validate_json(ground_truth_json)
        actual_dict = extraction.parsed
        validated_actual = None
        if actual_dict is not None:
            try:
                InvoiceExtraction.model_validate(actual_dict)
                validated_actual = actual_dict
            except Exception:  # noqa: BLE001 - schema-invalid output is scored as a parse failure, not a crash
                validated_actual = None
        diff_result = diff_invoice(expected, validated_actual)
        status = "success"
        raw_output = extraction.raw_text
        parsed_json = json.dumps(actual_dict) if actual_dict is not None else None
        diff_json = diff_result.model_dump_json()
        mistake_count = diff_result.mistake_count
        error_message = None
        duration_ms = extraction.duration_ms

    await db.complete_result(
        result_id,
        run_id,
        status=status,
        raw_output=raw_output,
        parsed_json=parsed_json,
        diff_json=diff_json,
        mistake_count=mistake_count,
        error_message=error_message,
        duration_ms=duration_ms,
    )
    run = await db.get_run(run_id)
    await manager.broadcast(
        run_id,
        {
            "type": "result_update",
            "result_id": result_id,
            "model_id": model_id,
            "invoice_stem": invoice_stem,
            "status": status,
            "mistake_count": mistake_count,
            "error_message": error_message,
        },
    )
    if run is not None:
        await manager.broadcast(
            run_id, {"type": "progress", "completed": run["completed_pairs"], "total": run["total_pairs"]}
        )

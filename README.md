# Invoice Scan Comparison Tool

Evaluate how different LLMs (local, via Ollama, and cloud, via Anthropic) perform at extracting
structured data from scanned legal invoices. Point it at a folder of invoices (PDF or image) plus
a matching folder of ground-truth JSON files, pick one or more models, and watch results stream in
live: per-invoice, per-model extraction results, a rule-based diff describing exactly what each
model got wrong, and a summary of mistake counts per model and per model+invoice.

## Important: Ollama runs on your Mac, not in Docker

**`docker compose up` alone is *not* fully self-contained for local-model runs.** Docker Desktop on
macOS cannot pass through the Apple Silicon GPU to a Linux container, so an Ollama server running
*inside* the container would be slow, CPU-only inference. Instead:

- **Anthropic models** (`claude-opus-4-8`, `claude-sonnet-5`, `claude-haiku-4-5`) work with just
  `docker compose up` plus a valid `ANTHROPIC_API_KEY` — no extra setup.
- **Ollama models** require Ollama installed and running **natively on your Mac** (so it gets Metal
  GPU acceleration) *before* you select an Ollama model in the UI. The app container reaches it at
  `http://host.docker.internal:11434`.

```bash
brew install ollama
ollama serve                 # in one terminal, or run the Ollama.app
ollama pull llama3.2-vision  # or another vision-capable model
```

## Setup

1. Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` if you want to evaluate Claude models.
2. `docker compose up --build`
3. Open http://localhost:8000

The app ships with three tiny synthetic sample invoices in `data/invoices/` (two PDFs, one PNG)
and matching ground truth in `data/ground_truth/`, so you can try a run immediately.

## Pages

- **Home** (`/`) — pick models, edit the extraction prompt, and start a run. On submit you're
  redirected to that run's own page.
- **Invoices** (`/invoices`) — lists every invoice file with its ground-truth status
  (valid/invalid/missing), and is where you upload new invoices. Uploaded files land directly in
  `data/invoices/` — the same folder used by every run. Add a matching ground-truth JSON file into
  `data/ground_truth/` separately, named after the invoice's filename stem (e.g. `my_invoice.pdf`
  needs `my_invoice.json`) to make it scoreable. The ground truth JSON must match the extraction
  schema in `app/models/invoice.py` (`InvoiceExtraction`) — see the sample files in
  `data/ground_truth/` for the shape. Both directories are Docker volumes, so changes on the host
  are picked up without a rebuild.
- **Runs** (`/runs`) — every run ever started, with its start time, status, and models. Click one
  to open its detail page (live progress while running, full summary once complete).

### Avoiding accidental re-runs

Every run is fingerprinted with a checksum over everything that determines its outcome: the bytes
of every invoice file, the bytes of every matched ground-truth file, the exact prompt text, and
the selected models (including, for Ollama models, the model's content digest — so a model
silently re-pulled under the same name still counts as different). If you start a run that's an
exact match for a previously *completed* run, the Home page shows a warning with a link to the
existing run instead of silently re-running it; you can still proceed via "Run anyway."

## Development (without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload
```

Note: running outside Docker without `poppler-utils` installed will make the Ollama PDF path fail
(`pdf2image` shells out to `pdftoppm`). Install it via `brew install poppler` if you need to
exercise that path locally. It is not required for the Anthropic provider (which sends PDFs
natively) or for image-only invoices.

## Architecture

- **Backend**: FastAPI + SQLite (`aiosqlite`), in-process `asyncio` orchestration — no message
  queue or broker; this is a single-user internal tool.
- **Frontend**: server-rendered Jinja2 + vanilla JS + WebSocket for live updates — no build step.
- **Providers**: `app/providers/` defines a small `BaseProvider` interface (`AnthropicProvider`,
  `OllamaProvider`) so another provider (OpenAI, Gemini, ...) could be added later without
  redesigning the rest of the app.
- **Comparison**: `app/diff/engine.py` does a deterministic, rule-based field-by-field diff
  (missing/extra fields, wrong values, numeric tolerance, date normalization, line-item alignment)
  — no LLM is used to describe failures.
- **Run fingerprinting**: `app/orchestrator/checksum.py` hashes the run's inputs so an identical
  run can be detected before it's re-executed (see "Avoiding accidental re-runs" above).

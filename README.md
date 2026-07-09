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

## Using your own invoices

Drop invoice files (`.pdf`, `.png`, `.jpg`) into `data/invoices/`, and a matching ground-truth JSON
file into `data/ground_truth/` named after the invoice's filename stem (e.g. `my_invoice.pdf` needs
`my_invoice.json`). The ground truth JSON must match the extraction schema in
`app/models/invoice.py` (`InvoiceExtraction`) — see the sample files in `data/ground_truth/` for
the shape. Both directories are Docker volumes, so changes on the host are picked up without a
rebuild; restart is not needed, just start a new run from the UI.

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

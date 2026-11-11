# AI-Powered Document Intelligence System

Automates invoice document processing: upload PDFs, scanned images, Excel and CSV files → OCR / parse → extract structured invoice data → validate → search via API and web UI.

Built for the **AI Engineer — Project: AI-Powered Document Intelligence System** assignment (5-day deadline). All 7 tasks are implemented; see `evaluation/evaluation_report.md` for measured metrics on a labeled 20-document dataset.

## Quick start

```bash
# 1. Backend (Python 3.12)
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
# OCR engine (scanned PDFs/images need it; digital PDFs and spreadsheets work without it)
sudo apt install tesseract-ocr        # or: pip install rapidocr-onnxruntime (fallback, see below)
.venv/bin/uvicorn app.main:app --app-dir backend --port 8000
# API docs: http://localhost:8000/docs

# 2. Frontend (Node 20)
cd frontend && npm install && npm run dev     # http://localhost:5173
# Production build: npm run build  (served from frontend/dist)

# 3. Tests + evaluation
.venv/bin/python scripts/generate_dataset.py   # 20 labeled synthetic invoices
.venv/bin/python scripts/evaluate.py          # writes evaluation/metrics.json
.venv/bin/pytest tests/ -v
```

## How it works

| Stage | Implementation |
|---|---|
| Ingest (Task 1) | `backend/app/ocr.py` — PyMuPDF text layer for digital PDFs; Tesseract OCR (300 dpi, contrast preprocessing) for scanned PDFs/images; `spreadsheets.py` — pandas/openpyxl, multi-sheet, header normalisation. Corrupt files fail cleanly as `failed` with a reason, never a 500. |
| Extraction (Task 2) | `backend/app/extract.py` — deterministic regex/heuristics first (invoice no, date, parties, money lines, line items), each with a 0–1 confidence. Optional LLM (`llm.py`, OpenAI-compatible, `LLM_API_KEY` set) fills only missing/low-confidence fields and never overwrites a confident value. **Missing = null, never invented.** |
| Validation (Task 3) | `backend/app/validate.py` — MISSING_FIELD, TOTAL_MISMATCH (subtotal+tax vs total, 1% tolerance), LINE_SUM_MISMATCH, DUPLICATE_INVOICE (same no + supplier), NEGATIVE_AMOUNT, LOW_CONFIDENCE. Any `error` → status `needs_review`. |
| API (Task 4) | FastAPI: `POST /documents/upload` (multi-file, 202 + background jobs), `GET /documents`, `GET /documents/{id}`, `GET /documents/{id}/status`, `GET /search`, `PATCH /documents/{id}/correct` (re-validates), `POST /documents/{id}/reprocess`. |
| DB + Search (Task 5) | SQLAlchemy + SQLite by default (`DATABASE_URL` → PostgreSQL in prod). Tables: documents, extractions, validation_errors, processing_history. Keyword search (SQL LIKE) + semantic search (TF-IDF cosine, scikit-learn; keyword-overlap fallback). |
| Frontend (Task 6) | React + Vite: multi-upload, live status polling, inspect + edit/correct extracted fields, validation issues, keyword/semantic/hybrid search. |
| Tests + Eval (Task 7) | `pytest` (extraction, validation, API incl. corrupt-file + reprocess). `scripts/evaluate.py` measures per-field accuracy, document success rate, failure rate, processing time on 20 labeled invoices. |

## Design decisions (why, not just what)

- **Deterministic extraction first, LLM optional.** Invoice fields are highly regular; regex gives auditable, reproducible results with no hallucination risk and zero API cost. The LLM is a filler, not the extractor — and the evaluated configuration runs with **no API key at all**.
- **SQLite by default, PostgreSQL by env var.** The assignment needs a working system, not a Docker-compose ceremony to demo it. One env var switches to Postgres; schema is identical.
- **In-process background jobs by default.** FastAPI `BackgroundTasks` keeps the demo dependency-free. For production scale the same `process_document()` is the worker body — run it under Celery/RQ with `REDIS_URL` (see `ARCHITECTURE.md`).
- **TF-IDF semantic search, not a vector DB.** For a corpus of thousands of invoices TF-IDF cosine is fast, exact, and needs no embedding service or vector store. The search layer is isolated (`search.py`), so swapping in pgvector/Chroma is a one-module change; the trade-off is documented in `ARCHITECTURE.md`.
- **Never invent values.** Every field carries a confidence; low-confidence or missing fields are flagged for manual review instead of being guessed.

## Hosting

**Quick demo, no account (Cloudflare Quick Tunnel).** The backend serves
the built frontend from the same origin (see `main.py`, static mount at the
end), so one tunnel exposes the whole app:

```bash
.venv/bin/uvicorn app.main:app --app-dir backend --port 8000
cloudflared tunnel --url http://localhost:8000
# -> https://<random-words>.trycloudflare.com  (public, HTTPS, no signup)
```

No Cloudflare account, DNS record or open port needed — one command, and the
URL dies when you stop `cloudflared`. Limits: temporary random URL, no
uptime guarantee, not for production. If UDP is blocked on your network, add
`--protocol http2`. This is the no-account method: **Cloudflare Pages
itself always requires a (free) account** — there is no anonymous Pages
deploy.

**Permanent hosting (free account).** Frontend → Cloudflare Pages
(dashboard → Workers & Pages → Create → Pages, or `wrangler pages deploy
frontend/dist`), backend → keep FastAPI on a server/PC and expose it with a
*named* Cloudflare Tunnel on your own domain. The frontend talks to the
backend relatively when served from it, or set `VITE_API_URL` to the
backend's public URL before `npm run build`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./backend/data/app.db` | PostgreSQL URL for production |
| `DATA_DIR` | `backend/data` | Uploads + SQLite file |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | unset / OpenAI / gpt-4o-mini | Enable optional LLM filler |
| `MAX_UPLOAD_MB` | 50 | Per-file upload limit |

## Project layout

```
backend/app/        FastAPI app: main, jobs (pipeline), ocr, spreadsheets,
                    extract, validate, llm, search, models, config
frontend/src/       React + Vite UI
tests/              pytest: extraction, validation, API
scripts/            generate_dataset.py, evaluate.py
data/samples/       20 generated invoices (PDF / scanned PDF / PNG / XLSX / CSV)
data/labeled/       ground_truth.json
evaluation/         metrics.json + evaluation_report.md
docs/               AI_PROMPTS.md, WALKTHROUGH.md, DISCLOSURE.md
ARCHITECTURE.md     Diagram, DB schema, scaling + security notes
```

## Security

Uploads are type-checked by extension and size-limited; files are stored by SHA-256 hash, never by user-supplied name; no file content is executed; the API has no auth in this demo build — add JWT/OAuth2 + HTTPS before exposing it (see `ARCHITECTURE.md` § Security).

## AI-assisted development disclosure

See `docs/DISCLOSURE.md`. The extraction core is deterministic code, not model output; the LLM filler prompt is in `docs/AI_PROMPTS.md`.

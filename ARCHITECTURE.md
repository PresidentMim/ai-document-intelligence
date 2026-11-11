# Architecture

## System diagram

```mermaid
flowchart LR
    U[User / Browser] --> FE[React + Vite UI<br/>upload · progress · review · search]
    FE -->|REST / JSON| API[FastAPI<br/>main.py]
    API --> Q[BackgroundTasks<br/>in-process queue]
    Q --> P[Pipeline — jobs.process_document]
    P --> T[Text: PyMuPDF text layer]
    P --> O[OCR: Tesseract 300dpi<br/>+ RapidOCR fallback]
    P --> S[Spreadsheets: pandas/openpyxl]
    T & O & S --> E[Extraction<br/>regex first, LLM filler]
    E --> V[Validation rules]
    V --> DB[(SQLite default<br/>PostgreSQL via DATABASE_URL)]
    API --> SR[Search: keyword LIKE<br/>+ TF-IDF cosine]
    SR --> DB
    E -.->|only if LLM_API_KEY set| LLM[OpenAI-compatible LLM]
```

## Request flow (one upload)

1. `POST /documents/upload` — files validated (type, ≤50 MB), stored by SHA-256, one `documents` row each with status `queued`, 202 returned immediately.
2. Background job `process_document` runs: text/OCR/spreadsheet parse → extraction → validation → `done` / `needs_review` / `failed`. Every step is written to `processing_history` with timing.
3. `GET /documents/{id}/status` polls progress; the UI polls every 3 s.
4. Correction (`PATCH …/correct`) re-runs validation and updates status. Failed jobs can be re-queued (`POST …/reprocess`) without re-uploading.

## Database schema

```mermaid
erDiagram
    documents ||--o| extractions : has
    documents ||--o{ validation_errors : has
    documents ||--o{ processing_history : has
    documents {
        int id PK
        string original_filename
        string file_type
        string sha256
        int page_count
        string status
        text extracted_text
        int ocr_used
        datetime created_at
    }
    extractions {
        int document_id FK
        string invoice_number
        string invoice_date
        string supplier_name
        string customer_name
        float subtotal
        float tax
        float total
        string currency
        text line_items_json
        text confidence_json
    }
    validation_errors {
        int document_id FK
        string code
        string field
        string severity
        string message
    }
    processing_history {
        int document_id FK
        string step
        string status
        int duration_ms
    }
```

## Scaling (what changes at 1,000 pages/day and beyond)

- **Queue:** replace `BackgroundTasks` with Celery/RQ on Redis (`REDIS_URL`); `process_document()` is already the worker body, no pipeline rewrite.
- **OCR:** Tesseract is CPU-bound (~1–3 s/page at 300 dpi). Scale workers horizontally; cache OCR text by file SHA-256 so re-uploads skip OCR.
- **Search:** TF-IDF is rebuilt per query over the corpus — fine for thousands of docs, not millions. At that scale move to pgvector or Chroma with an embedding model; `search.py` is the only module that changes.
- **Storage:** move uploads from local disk to S3-compatible object storage; store only the object key in `documents.filename`.
- **DB:** SQLite → PostgreSQL (`DATABASE_URL`); add indexes already present on `status`, `invoice_number`, `supplier_name`.

## Failure handling

| Failure | Behaviour |
|---|---|
| Corrupt PDF / unreadable spreadsheet | `failed`, human-readable `error_message`, original kept for reprocess |
| Scanned doc, no OCR engine installed | `failed` naming the missing binary (Tesseract) instead of silent garbage |
| LLM unreachable / no key | Skipped silently; deterministic extraction still runs |
| Total mismatch / missing field / duplicate | `needs_review` + validation errors, never silently accepted |
| Duplicate upload (same SHA-256) | Stored once on disk; each upload still gets its own document row + duplicate-invoice flag if the invoice number repeats |

## Security

- Uploads: extension allow-list, 50 MB cap, stored under a hash name (no path traversal via filename), never executed.
- No secrets in code; LLM key via env only. CORS is wide open (`*`) for the demo — restrict to the frontend origin in production.
- **Not yet in this build (stated honestly):** authentication (add JWT/OAuth2), HTTPS termination, per-user document isolation, rate limiting, virus scanning of uploads. All are one-layer additions, listed here so the gap is explicit rather than hidden.

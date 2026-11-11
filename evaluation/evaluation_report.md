# Evaluation report — AI-Powered Document Intelligence System

**How to reproduce:** `python3 scripts/generate_dataset.py` then
`python3 scripts/evaluate.py` (writes `evaluation/metrics.json`).
Tests: `pytest tests/ -v`. All numbers below are copied from those two
runs on 2026-11-11 in this VM (Python 3.12, 4 CPU, no GPU).
**Evaluated configuration: no LLM key** — deterministic extraction only.
OCR engine in this run: RapidOCR (Tesseract preferred when installed;
`apt update` on this VM was still running, so Tesseract was unavailable —
the code tries Tesseract first and falls back to RapidOCR).

## Dataset

20 synthetic labeled invoices (`data/samples/`, truth in
`data/labeled/ground_truth.json`), fictional suppliers/customers, no real data:
8 digital PDFs, 4 scanned (image-only) PDFs, 4 PNG images, 2 multi-sheet
XLSX, 2 CSV. Two intentional defects: invoice_18 has a total $50 too high
(validation test), invoice_19 has no invoice number in the source document
(missing-field test).

## Results

| Metric | Value |
|---|---|
| Documents evaluated | 20 |
| Fully correct documents (all 8 fields) | 19 / 20 (**95.0% document success rate**) |
| Failed documents | 0 / 20 (**0.0% failure rate**) |
| Mean field accuracy (8 fields × 20 docs) | **99.4%** |
| Mean processing time | **3.07 s / document** (total 61.4 s) |

### Per-field accuracy

| Field | Accuracy |
|---|---|
| invoice_number | 95.0% (19/20) |
| invoice_date | 100% |
| supplier_name | 100% |
| customer_name | 100% |
| subtotal | 100% |
| tax | 100% |
| total | 100% |
| currency | 100% |

### Per-type processing time

| Type | Mean time | Notes |
|---|---|---|
| Digital PDF | ~0.01 s | text layer, no OCR |
| Scanned PDF | ~10.4 s | OCR, 1 page @ RapidOCR |
| PNG image | ~4.7 s | OCR |
| XLSX / CSV | ~0.1 s | pandas parse, no OCR |

### The one miss, explained

invoice_19.csv scored 7/8 — its invoice number is **absent from the source
file by design** (the missing-field defect). The extractor correctly returned
`null` instead of inventing a number, and validation flags it
`MISSING_FIELD` → `needs_review`. That is the intended behaviour, not an
extraction error.

## Validation (separate from extraction accuracy)

Verified live via the API (not just unit tests): invoice_18 (total $50 high)
→ status `needs_review`, `TOTAL_MISMATCH`; correcting the total via
`PATCH /documents/{id}/correct` re-ran validation and flipped it to `done`
with no errors. invoice_19 → `MISSING_FIELD`. A corrupt PDF upload →
`failed` with a readable error, reprocessable without re-upload.

## Test results

`pytest tests/` — **13 passed** (extraction 3, validation 5, API 5):
upload + background processing, keyword/semantic search, manual correction
with re-validation, unsupported-type rejection (400), corrupt-file failure
and reprocess (202). Run output is in the repo; no failures.

## Limitations (honest)

- **Synthetic data.** Invoices are clean, templated, English-only. Real-world
  accuracy on messy scans, handwriting, or unusual layouts will be lower;
  the LLM filler (`LLM_API_KEY`) exists for exactly those cases and was not
  part of this evaluation.
- **OCR speed.** ~10 s/page on CPU with RapidOCR; Tesseract is typically
  faster and should be installed where available.
- **Semantic search** is TF-IDF cosine — good for thousands of documents,
  not a replacement for a vector DB at very large scale (see ARCHITECTURE.md).
- **No auth** in this build — add JWT/OAuth2 before exposing the API.
- **Walkthrough video:** not recorded in this environment; follow
  `docs/WALKTHROUGH.md` (4-minute script, reproducible from the API).

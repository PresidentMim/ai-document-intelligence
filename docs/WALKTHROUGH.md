# Walkthrough script (for the recorded demo video)

Record a screen capture following this script (~4 minutes). Commands assume
the repo root and the backend already running on :8000, frontend on :5173.

**0:00 — Intro (30s)**
"Document Intelligence: upload invoices in any format, get structured,
validated, searchable data." Show README + architecture diagram.

**0:30 — Upload (45s)**
Frontend → choose `data/samples/invoice_01.pdf`, `invoice_09_scanned.pdf`,
`invoice_17.xlsx`, `invoice_19.csv` together → Upload. Status moves
queued → processing → done / needs_review live.

**1:15 — Inspect (60s)**
Open invoice_01: extracted fields + confidence, line items, processing
history with timings. Open invoice_18 (total mismatch): validation error
`TOTAL_MISMATCH` shown, status `needs_review`.

**2:15 — Correct (45s)**
Edit the wrong total on invoice_18, Save correction → validation re-runs,
status flips to done. Show `PATCH /documents/{id}/correct` in API docs.

**3:00 — Search (45s)**
Search "Acme" (keyword), then "office supplies invoice" (semantic) —
same document surfaces both ways. Filter the list by status `needs_review`.

**3:45 — Failure path (30s)**
Upload a corrupt PDF → status `failed` with a readable error → Reprocess
button. Close: "Tests: pytest; evaluation: scripts/evaluate.py — metrics
in evaluation/metrics.json."

## If recording is not possible

The same flow is reproducible from the API alone — see README Quick start
and `evaluation/evaluation_report.md` § Reproduction.

# AI prompts & disclosure

## LLM extraction prompt (backend/app/llm.py)

```
Extract invoice fields from the document text below.
Return ONLY valid JSON with keys: invoice_number, invoice_date (YYYY-MM-DD),
supplier_name, customer_name, subtotal, tax, total, currency (ISO code),
line_items (list of {description, quantity, unit_price, amount}).
Rules: use null for any field you cannot find — NEVER invent a value.
Give a confidence 0..1 per field in a second object "confidence".
Document text:
{text}
```

Model: `gpt-4o-mini` by default (env `LLM_MODEL`), temperature 0, JSON mode.
The LLM runs **only** when `LLM_API_KEY` is set, and its output is merged by
`extract.merge_extractions`, which fills only null/low-confidence fields and
never overwrites a confident deterministic value. LLM failure never fails a job.

## Evaluated configuration

The evaluation in `evaluation/evaluation_report.md` was run **without any LLM
key** — fully offline, deterministic extraction only. Any LLM improvement on
top of those numbers would be additional, not assumed.

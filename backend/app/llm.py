"""Optional LLM extraction (OpenAI-compatible API).

OFF by default: it runs only when LLM_API_KEY is set. The prompt
(docs/AI_PROMPTS.md) instructs the model to return null for anything
it cannot find and to give a confidence per field. The result is
merged by extract.merge_extractions, which never overwrites a
confident deterministic value. No API key -> the system is fully
offline and deterministic; that is the evaluated configuration.
"""
import json
import httpx
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

PROMPT = """Extract invoice fields from the document text below.
Return ONLY valid JSON with keys: invoice_number, invoice_date (YYYY-MM-DD),
supplier_name, customer_name, subtotal, tax, total, currency (ISO code),
line_items (list of {description, quantity, unit_price, amount}).
Rules: use null for any field you cannot find — NEVER invent a value.
Give a confidence 0..1 per field in a second object "confidence".
Document text:
{text}
"""

def llm_extract(text: str) -> dict | None:
    if not LLM_API_KEY:
        return None
    try:
        r = httpx.post(f"{LLM_BASE_URL}/chat/completions", headers={
            "Authorization": f"Bearer {LLM_API_KEY}"}, json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": PROMPT.format(text=text[:12000])}],
            "temperature": 0, "response_format": {"type": "json_object"}},
            timeout=60)
        r.raise_for_status()
        data = json.loads(r.json()["choices"][0]["message"]["content"])
        fields = {k: data.get(k) for k in
                  ("invoice_number", "invoice_date", "supplier_name", "customer_name",
                   "subtotal", "tax", "total", "currency", "line_items")}
        return {"fields": fields, "confidence": data.get("confidence", {})}
    except Exception:
        return None  # LLM failure must never fail the whole job

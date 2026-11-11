"""Invoice extraction — deterministic first, LLM only as a filler.

Principle (Task 2): NEVER invent a value. A field is returned only
when evidence supports it; otherwise it is null with confidence 0
and a `missing` note. Regex/heuristics give high-precision fields
(invoice no, amounts, dates); the optional LLM (see llm.py) may fill
supplier/customer/line-items the regex missed, and only with a
confidence score. Every field carries a 0..1 confidence.
"""
import json, re
from datetime import datetime

MONEY = r"[\$€£¥₹]?\s?([\d,]+(?:\.\d{2})?)"
DATE_RES = [
    r"(\d{4}-\d{2}-\d{2})", r"(\d{2}/\d{2}/\d{4})", r"(\d{2}-\d{2}-\d{4})",
    r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})",
]
CURRENCIES = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR"}

def _money(s):
    try:
        return float(str(s).replace(",", "").replace("$", "").replace("€", "")
                     .replace("£", "").replace("₹", "").strip())
    except Exception:
        return None

def _find(pattern, text, flags=re.I):
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None

def _parse_date(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except Exception:
            continue
    return s.strip()

def extract_from_text(text: str) -> dict:
    t = text or ""
    out = {"invoice_number": None, "invoice_date": None, "supplier_name": None,
           "customer_name": None, "subtotal": None, "tax": None, "total": None,
           "currency": None, "line_items": []}
    conf = {k: 0.0 for k in out}
    # Invoice number — label ("Invoice Number/No/#:") is required, and the
    # token must contain a digit, so the bare heading "INVOICE" alone
    # can never be captured as the number.
    v = _find(r"\binvoice\s*(?:no\.?|number|#|id)\s*[:#]?\s*([A-Za-z0-9\-/]*\d[A-Za-z0-9\-/]{1,29})", t)
    if not v:
        v = _find(r"\binvoice\s*[:#]\s*([A-Za-z0-9\-/]*\d[A-Za-z0-9\-/]{1,29})", t)
    if v:
        out["invoice_number"] = v; conf["invoice_number"] = 0.95
    # Date
    for pat in DATE_RES:
        v = _find(r"(?:invoice\s*date|date\s*(?:of\s*issue)?|issued)\s*[:#]?\s*" + pat, t)
        if v:
            out["invoice_date"] = _parse_date(v); conf["invoice_date"] = 0.9; break
    if not out["invoice_date"]:
        m = re.search(DATE_RES[0], t)
        if m:
            out["invoice_date"] = _parse_date(m.group(1)); conf["invoice_date"] = 0.5
    # Parties — "From:/Bill From:/Supplier:" and "To:/Bill To:/Customer:"
    v = _find(r"(?:supplier|from|bill\s*from|vendor)\s*[:]\s*([^\n\r]{2,80})", t)
    if v:
        out["supplier_name"] = v.strip(); conf["supplier_name"] = 0.85
    v = _find(r"(?:customer|bill\s*to|to|client)\s*[:]\s*([^\n\r]{2,80})", t)
    if v:
        out["customer_name"] = v.strip(); conf["customer_name"] = 0.85
    # Money lines — labelled lines win over bare numbers. \b guards matter:
    # "total" must not match inside "subtotal".
    for field, label in [("subtotal", r"\bsubtotal\b"), ("tax", r"\b(?:tax|vat|gst)\b"),
                         ("total", r"(?:(?<!sub)\btotal\b|amount\s*due|grand\s*total|balance\s*due)")]:
        v = _find(rf"(?:{label})\s*[:$€£₹]?\s*{MONEY}", t)
        if v and _money(v) is not None:
            out[field] = _money(v); conf[field] = 0.92
    # Currency from symbol, else from an explicit code
    for sym, code in CURRENCIES.items():
        if sym in t:
            out["currency"] = code; conf["currency"] = 0.8; break
    if not out["currency"]:
        v = _find(r"\b(USD|EUR|GBP|INR|BDT|JPY)\b", t)
        if v:
            out["currency"] = v.upper(); conf["currency"] = 0.9
    # Line items: rows like "Widget A  2  25.00  50.00" or "2 x Widget @ 25.00".
    # Second pattern handles OCR text where spaces collapse
    # ("WidgetA225.0050.00"): lazy description, qty digit, two money tokens.
    items = []
    for line in t.splitlines():
        line = line.strip()
        if re.search(r"subtotal|total|tax", line, re.I):
            continue
        m = re.match(r"\s*(.+?)\s+(\d+)\s*[x×]?\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$", line)
        if not m:
            m = re.match(r"(.+?)(\d)\s*([\d,]+\.\d{2})\s*([\d,]+\.\d{2})\s*$", line)
        if m:
            items.append({"description": m.group(1).strip(), "quantity": int(m.group(2)),
                          "unit_price": _money(m.group(3)), "amount": _money(m.group(4))})
    if items:
        out["line_items"] = items; conf["line_items"] = 0.75
    return {"fields": out, "confidence": conf}

def extract_from_table(sheets: dict) -> dict:
    """Spreadsheet path: map known columns to invoice fields (first data row)."""
    out = {"invoice_number": None, "invoice_date": None, "supplier_name": None,
           "customer_name": None, "subtotal": None, "tax": None, "total": None,
           "currency": None, "line_items": []}
    conf = {k: 0.0 for k in out}
    rows = []
    for sheet_rows in sheets.values():
        rows.extend(sheet_rows)
    if not rows:
        return {"fields": out, "confidence": conf}
    def col_from(row, *names):
        for n in names:
            if n in row and str(row[n]).strip():
                return str(row[n]).strip()
        return None
    # Scalar fields may live on any row / any sheet (e.g. a "Totals" sheet),
    # so scan all rows and take the first non-empty value per field.
    first = rows[0]
    mapping = {"invoice_number": ("invoice_number", "invoice_no", "invoice", "number"),
               "supplier_name": ("supplier", "supplier_name", "vendor", "from"),
               "customer_name": ("customer", "customer_name", "client", "bill_to"),
               "currency": ("currency",)}
    for field, names in mapping.items():
        for r in rows:
            v = col_from(r, *names)
            if v:
                out[field] = v; conf[field] = 0.95; break
    for field in ("subtotal", "tax", "total"):
        for r in rows:
            v = col_from(r, field)
            if v and _money(v) is not None:
                out[field] = _money(v); conf[field] = 0.95; break
    for r in rows:
        v = col_from(r, "invoice_date", "date", "issued")
        if v:
            out["invoice_date"] = _parse_date(v); conf["invoice_date"] = 0.9; break
    # Line items: every row with a description + amount
    items = []
    for r in rows:
        desc = r.get("description") or r.get("item") or ""
        amt = _money(r.get("amount", "") or r.get("total", "") or "")
        if desc and amt is not None:
            try:
                qty = int(float(r.get("quantity") or r.get("qty") or 1))
            except Exception:
                qty = 1
            items.append({"description": str(desc).strip(), "quantity": qty,
                          "unit_price": _money(r.get("unit_price") or r.get("price") or "") or amt,
                          "amount": amt})
    if items:
        out["line_items"] = items; conf["line_items"] = 0.95
    return {"fields": out, "confidence": conf}

def merge_extractions(base: dict, extra: dict) -> dict:
    """Fill only null/low-confidence fields from the LLM result; never overwrite a confident regex value."""
    fields, conf = base["fields"], base["confidence"]
    for k, v in extra.get("fields", {}).items():
        if v in (None, "", []):
            continue
        if fields.get(k) in (None, "", []) or conf.get(k, 0) < 0.6:
            fields[k] = v; conf[k] = min(extra.get("confidence", {}).get(k, 0.6), 0.85)
    return {"fields": fields, "confidence": conf}

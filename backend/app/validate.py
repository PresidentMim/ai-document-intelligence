"""Validation rules (Task 3). Returns a list of {code, field, severity, message}.
Rules: MISSING_FIELD, TOTAL_MISMATCH (subtotal+tax != total, tolerance 0.01
or 1% — whichever larger, to allow rounding), LINE_SUM_MISMATCH,
DUPLICATE_INVOICE (same invoice_number + supplier, checked in the API
against the DB), NEGATIVE_AMOUNT, LOW_CONFIDENCE.
A document with any `error` severity -> status needs_review.
"""
from sqlalchemy.orm import Session
from .models import Document, Extraction

REQUIRED = ["invoice_number", "invoice_date", "supplier_name", "total"]

def validate(fields: dict, confidence: dict, db: Session, document_id: int) -> list:
    errs = []
    for f in REQUIRED:
        if fields.get(f) in (None, "", []):
            errs.append({"code": "MISSING_FIELD", "field": f, "severity": "error",
                         "message": f"Required field '{f}' could not be extracted."})
        elif confidence.get(f, 0) < 0.5:
            errs.append({"code": "LOW_CONFIDENCE", "field": f, "severity": "warning",
                         "message": f"Field '{f}' extracted with low confidence "
                                    f"({confidence.get(f, 0):.2f}); verify manually."})
    sub, tax, tot = fields.get("subtotal"), fields.get("tax"), fields.get("total")
    if sub is not None and tot is not None:
        expected = sub + (tax or 0)
        tol = max(0.01, abs(expected) * 0.01)
        if abs(expected - tot) > tol:
            errs.append({"code": "TOTAL_MISMATCH", "field": "total", "severity": "error",
                         "message": f"subtotal ({sub}) + tax ({tax or 0}) = {expected:.2f} "
                                    f"but total is {tot:.2f}."})
    items = fields.get("line_items") or []
    if items and sub is not None:
        s = sum((i.get("amount") or 0) for i in items)
        if abs(s - sub) > max(0.01, abs(sub) * 0.01):
            errs.append({"code": "LINE_SUM_MISMATCH", "field": "subtotal", "severity": "warning",
                         "message": f"Line items sum to {s:.2f} but subtotal is {sub:.2f}."})
    for f in ("subtotal", "tax", "total"):
        if fields.get(f) is not None and fields[f] < 0:
            errs.append({"code": "NEGATIVE_AMOUNT", "field": f, "severity": "error",
                         "message": f"{f} is negative ({fields[f]})."})
    # Duplicate: same invoice_number + supplier in another document
    inv, sup = fields.get("invoice_number"), fields.get("supplier_name")
    if inv:
        q = db.query(Document).join(Extraction).filter(
            Extraction.invoice_number == inv, Document.id != document_id)
        if sup:
            q = q.filter(Extraction.supplier_name == sup)
        if q.first():
            errs.append({"code": "DUPLICATE_INVOICE", "field": "invoice_number",
                         "severity": "error",
                         "message": f"Invoice '{inv}' from '{sup or 'unknown supplier'}' "
                                    "already exists in the system."})
    return errs

"""Processing pipeline (Tasks 1-3): upload -> text/OCR/spreadsheet ->
extraction -> validation -> done/needs_review/failed. Each step is
logged to processing_history with timing; a failure at any step marks
the document `failed` with a human-readable error and leaves the
original file intact for reprocessing (POST /documents/{id}/reprocess).
"""
import hashlib, json, time
from pathlib import Path
from sqlalchemy.orm import Session
from . import models
from .extract import extract_from_text, extract_from_table, merge_extractions
from .llm import llm_extract
from .ocr import extract_text
from .spreadsheets import parse_spreadsheet
from .validate import validate

def _log(db, doc_id, step, status, detail="", ms=0):
    db.add(models.ProcessingHistory(document_id=doc_id, step=step, status=status,
                                    detail=detail, duration_ms=ms))

def _set(db, doc, status, error=None):
    doc.status = status
    if error is not None:
        doc.error_message = error
    db.commit()

def process_document(db: Session, doc_id: int):
    doc = db.get(models.Document, doc_id)
    if not doc:
        return
    path = Path(doc.filename)
    t0 = time.time()
    _set(db, doc, models.JobStatus.PROCESSING.value)
    try:
        suffix = path.suffix.lower()
        if suffix in {".xlsx", ".xls", ".csv"}:
            t = time.time()
            parsed = parse_spreadsheet(path)
            doc.extracted_text, doc.sheet_names = parsed["text"], json.dumps(parsed["sheet_names"])
            doc.page_count = parsed["row_count"]
            _log(db, doc_id, "spreadsheet_parse", "ok", f"{len(parsed['sheet_names'])} sheets, {parsed['row_count']} rows", int((time.time()-t)*1000))
            result = extract_from_table(parsed["sheets"])
        elif suffix == ".pdf" or suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
            t = time.time()
            text, ocr_used, pages, detail = extract_text(path)
            doc.extracted_text, doc.ocr_used, doc.page_count = text, int(ocr_used), pages
            _log(db, doc_id, "text_extract", "ok", detail, int((time.time()-t)*1000))
            result = extract_from_text(text)
            llm = llm_extract(text)
            if llm:
                result = merge_extractions(result, llm)
                _log(db, doc_id, "llm_extract", "ok", "LLM filled missing fields only")
        else:
            raise ValueError(f"Unsupported file type: {suffix}")
        db.commit()
        fields, conf = result["fields"], result["confidence"]
        # Persist extraction
        db.add(models.Extraction(document_id=doc_id,
            invoice_number=fields.get("invoice_number"), invoice_date=fields.get("invoice_date"),
            supplier_name=fields.get("supplier_name"), customer_name=fields.get("customer_name"),
            subtotal=fields.get("subtotal"), tax=fields.get("tax"), total=fields.get("total"),
            currency=fields.get("currency"),
            line_items_json=json.dumps(fields.get("line_items") or []),
            confidence_json=json.dumps(conf), raw_json=json.dumps(fields)))
        errs = validate(fields, conf, db, doc_id)
        for e in errs:
            db.add(models.ValidationError(document_id=doc_id, **e))
        db.commit()
        has_error = any(e["severity"] == "error" for e in errs)
        _log(db, doc_id, "validate", "ok" if not has_error else "needs_review",
             f"{len(errs)} validation issue(s)", int((time.time()-t0)*1000))
        _set(db, doc, models.JobStatus.NEEDS_REVIEW.value if has_error else models.JobStatus.DONE.value)
        _log(db, doc_id, "done", doc.status, "", int((time.time()-t0)*1000))
    except Exception as e:
        db.rollback()
        doc = db.get(models.Document, doc_id)
        _log(db, doc_id, "failed", "failed", str(e)[:500], int((time.time()-t0)*1000))
        _set(db, doc, models.JobStatus.FAILED.value, error=str(e)[:500])

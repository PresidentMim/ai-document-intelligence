"""FastAPI backend (Task 4). Run: uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs
Endpoints: upload, list/filter, detail, status, search, correct, reprocess.
Background work uses BackgroundTasks (in-process queue); swap in
Redis + BullMQ/Celery by setting REDIS_URL — see ARCHITECTURE.md.
"""
import hashlib, json, shutil
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from . import models
from .config import ALLOWED_EXTS, MAX_UPLOAD_MB, UPLOAD_DIR
from .jobs import process_document
from .models import SessionLocal, init_db
from .search import keyword_search, semantic_search

app = FastAPI(title="Document Intelligence API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_db()

def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def doc_out(d: models.Document):
    e = d.extraction
    return {
        "id": d.id, "filename": d.original_filename, "file_type": d.file_type,
        "file_size": d.file_size, "page_count": d.page_count,
        "status": d.status, "error": d.error_message, "ocr_used": bool(d.ocr_used),
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "extraction": None if not e else {
            "invoice_number": e.invoice_number, "invoice_date": e.invoice_date,
            "supplier_name": e.supplier_name, "customer_name": e.customer_name,
            "subtotal": e.subtotal, "tax": e.tax, "total": e.total,
            "currency": e.currency, "line_items": json.loads(e.line_items_json or "[]"),
            "confidence": json.loads(e.confidence_json or "{}")},
        "validation_errors": [{"code": v.code, "field": v.field, "severity": v.severity,
                               "message": v.message} for v in d.validations],
        "history": [{"step": h.step, "status": h.status, "detail": h.detail,
                     "duration_ms": h.duration_ms} for h in d.history],
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/documents/upload", status_code=202)
async def upload(background_tasks: BackgroundTasks, files: list[UploadFile] = File(...)):
    """Accept multiple files. Each is queued; processing is async.
    Returns 202 with one job per file. Unsupported/corrupt files are
    still accepted and marked `failed` with a reason — never a 500."""
    db = SessionLocal()
    created = []
    try:
        for f in files:
            suffix = Path(f.filename or "").suffix.lower()
            if suffix not in ALLOWED_EXTS:
                raise HTTPException(400, f"Unsupported file type: {suffix}. "
                                    f"Allowed: {sorted(ALLOWED_EXTS)}")
            data = await f.read()
            if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
                raise HTTPException(413, f"{f.filename} exceeds {MAX_UPLOAD_MB} MB")
            sha = hashlib.sha256(data).hexdigest()
            stored = UPLOAD_DIR / f"{sha[:16]}{suffix}"
            stored.write_bytes(data)
            kind = ("pdf" if suffix == ".pdf" else
                    "image" if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff"} else
                    "spreadsheet" if suffix in {".xlsx", ".xls"} else "csv")
            doc = models.Document(filename=str(stored), original_filename=f.filename,
                                  file_type=kind, mime_type=f.content_type,
                                  file_size=len(data), sha256=sha, status="queued")
            db.add(doc); db.commit(); db.refresh(doc)
            background_tasks.add_task(process_document, SessionLocal(), doc.id)
            created.append({"id": doc.id, "filename": f.filename, "status": "queued"})
    finally:
        db.close()
    return {"jobs": created}

@app.get("/documents")
def list_documents(status: str | None = None, supplier: str | None = None,
                   q: str | None = None, limit: int = 50, offset: int = 0):
    db = SessionLocal()
    try:
        query = db.query(models.Document)
        if status:
            query = query.filter(models.Document.status == status)
        if supplier:
            query = query.join(models.Extraction).filter(
                models.Extraction.supplier_name.like(f"%{supplier}%"))
        if q:
            query = query.filter(models.Document.extracted_text.like(f"%{q}%"))
        total = query.count()
        docs = query.order_by(models.Document.id.desc()).offset(offset).limit(limit).all()
        return {"total": total, "documents": [doc_out(d) for d in docs]}
    finally:
        db.close()

@app.get("/documents/{doc_id}")
def get_document(doc_id: int):
    db = SessionLocal()
    try:
        d = db.get(models.Document, doc_id)
        if not d:
            raise HTTPException(404, "Document not found")
        return doc_out(d)
    finally:
        db.close()

@app.get("/documents/{doc_id}/status")
def get_status(doc_id: int):
    db = SessionLocal()
    try:
        d = db.get(models.Document, doc_id)
        if not d:
            raise HTTPException(404, "Document not found")
        return {"id": d.id, "status": d.status, "error": d.error_message,
                "history": [{"step": h.step, "status": h.status, "detail": h.detail}
                            for h in d.history]}
    finally:
        db.close()

@app.get("/search")
def search(q: str, mode: str = "hybrid", limit: int = 20):
    """Keyword, semantic (TF-IDF cosine), or hybrid (both, deduped)."""
    db = SessionLocal()
    try:
        if mode == "keyword":
            docs = keyword_search(db, q)[:limit]
            return {"mode": mode, "query": q, "results": [
                {"id": d.id, "filename": d.original_filename, "status": d.status,
                 "score": 1.0} for d in docs]}
        scored = semantic_search(db, q, top_k=limit)
        if mode == "hybrid":
            kw = {d.id for d in keyword_search(db, q)}
            scored = [(d, max(s, 0.5 if d.id in kw else s)) for d, s in scored]
            scored.sort(key=lambda x: -x[1])
        return {"mode": mode, "query": q, "results": [
            {"id": d.id, "filename": d.original_filename, "status": d.status,
             "score": round(s, 3), "supplier": d.extraction.supplier_name if d.extraction else None,
             "invoice_number": d.extraction.invoice_number if d.extraction else None}
            for d, s in scored]}
    finally:
        db.close()

@app.patch("/documents/{doc_id}/correct")
async def correct(doc_id: int, payload: dict):
    """Manual correction (Task 4/6): user fixes a field; the correction
    is stored, validation re-runs, and status updates. `payload` is a
    partial extraction, e.g. {"total": 1250.00, "invoice_number": "INV-9"}."""
    db = SessionLocal()
    try:
        d = db.get(models.Document, doc_id)
        if not d or not d.extraction:
            raise HTTPException(404, "Document or extraction not found")
        e = d.extraction
        for k in ("invoice_number", "invoice_date", "supplier_name", "customer_name",
                  "subtotal", "tax", "total", "currency"):
            if k in payload:
                setattr(e, k, payload[k])
        if "line_items" in payload:
            e.line_items_json = json.dumps(payload["line_items"])
        # Re-validate with the corrected values
        from .validate import validate
        fields = {"invoice_number": e.invoice_number, "invoice_date": e.invoice_date,
                  "supplier_name": e.supplier_name, "customer_name": e.customer_name,
                  "subtotal": e.subtotal, "tax": e.tax, "total": e.total,
                  "currency": e.currency, "line_items": json.loads(e.line_items_json or "[]")}
        conf = json.loads(e.confidence_json or "{}")
        for v in list(d.validations):
            db.delete(v)
        errs = validate(fields, conf, db, doc_id)
        for er in errs:
            db.add(models.ValidationError(document_id=doc_id, **er))
        d.status = "needs_review" if any(x["severity"] == "error" for x in errs) else "done"
        db.add(models.ProcessingHistory(document_id=doc_id, step="manual_correction",
                                        status="ok", detail=f"Corrected fields: {list(payload)}"))
        db.commit()
        return doc_out(d)
    finally:
        db.close()

@app.post("/documents/{doc_id}/reprocess", status_code=202)
async def reprocess(doc_id: int, background_tasks: BackgroundTasks):
    db = SessionLocal()
    try:
        d = db.get(models.Document, doc_id)
        if not d:
            raise HTTPException(404, "Document not found")
        for v in list(d.validations):
            db.delete(v)
        if d.extraction:
            db.delete(d.extraction)
        d.status, d.error_message = "queued", None
        db.commit()
        background_tasks.add_task(process_document, SessionLocal(), doc_id)
        return {"id": doc_id, "status": "queued"}
    finally:
        db.close()

# Serve the built React frontend from the same origin when it exists
# (frontend/dist after `npm run build`). This mount MUST stay last: routes
# defined above take precedence, so /health, /documents, /search keep
# working and only non-API paths fall through to the frontend. One port
# then serves the whole app — which is also what makes a single
# Cloudflare Quick Tunnel enough to share it publicly.
from pathlib import Path as _Path
_DIST = _Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")

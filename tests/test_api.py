"""API tests via FastAPI TestClient. Upload -> poll status -> correct -> reprocess.
Uses a temp DATA_DIR so tests never touch the real database."""
import os, sys, tempfile, time
from pathlib import Path
tmp = tempfile.mkdtemp()
os.environ["DATA_DIR"] = tmp
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SAMPLE_PDF = Path(__file__).resolve().parent.parent / "data/samples/invoice_01.pdf"

def _wait_done(doc_id, timeout=30):
    for _ in range(timeout * 2):
        r = client.get(f"/documents/{doc_id}/status")
        if r.json()["status"] in ("done", "needs_review", "failed"):
            return r.json()["status"]
        time.sleep(0.5)
    return "timeout"

def test_health():
    assert client.get("/health").json() == {"status": "ok"}

def test_upload_and_process_pdf():
    assert SAMPLE_PDF.exists(), "run scripts/generate_dataset.py first"
    r = client.post("/documents/upload", files=[("files", ("invoice_01.pdf", SAMPLE_PDF.read_bytes(), "application/pdf"))])
    assert r.status_code == 202
    doc_id = r.json()["jobs"][0]["id"]
    assert _wait_done(doc_id) in ("done", "needs_review")
    d = client.get(f"/documents/{doc_id}").json()
    assert d["extraction"]["invoice_number"] == "INV-1000"
    assert d["extraction"]["total"] == d["extraction"]["subtotal"] + d["extraction"]["tax"]

def test_unsupported_file_rejected():
    r = client.post("/documents/upload", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400

def test_search_and_correct():
    r = client.get("/search?q=INV-1000&mode=keyword")
    assert r.status_code == 200 and len(r.json()["results"]) >= 1
    doc_id = r.json()["results"][0]["id"]
    r = client.patch(f"/documents/{doc_id}/correct", json={"total": 9999.0})
    assert r.status_code == 200
    assert any(e["code"] == "TOTAL_MISMATCH" for e in r.json()["validation_errors"])
    # fix it back
    d = client.get(f"/documents/{doc_id}").json()
    client.patch(f"/documents/{doc_id}/correct",
                 json={"total": d["extraction"]["subtotal"] + d["extraction"]["tax"]})

def test_reprocess_failed_job():
    r = client.post("/documents/upload", files=[("files", ("bad.pdf", b"not a pdf at all", "application/pdf"))])
    doc_id = r.json()["jobs"][0]["id"]
    assert _wait_done(doc_id) == "failed"
    r = client.post(f"/documents/{doc_id}/reprocess")
    assert r.status_code == 202 and r.json()["status"] == "queued"

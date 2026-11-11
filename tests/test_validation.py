import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.validate import validate

class FakeDB:
    class Q:
        def join(self, *a): return self
        def filter(self, *a): return self
        def first(self): return None
    def query(self, *a): return self.Q()

def good():
    return {"invoice_number": "INV-1", "invoice_date": "2026-10-01",
            "supplier_name": "Acme", "customer_name": "Northwind",
            "subtotal": 100.0, "tax": 10.0, "total": 110.0, "currency": "USD",
            "line_items": [{"description": "X", "quantity": 1, "unit_price": 100.0, "amount": 100.0}]}

def test_valid_invoice_has_no_errors():
    assert validate(good(), {k: 0.9 for k in good()}, FakeDB(), 1) == []

def test_total_mismatch_flagged():
    f = good(); f["total"] = 999.0
    codes = [e["code"] for e in validate(f, {k: 0.9 for k in f}, FakeDB(), 1)]
    assert "TOTAL_MISMATCH" in codes

def test_missing_field_flagged():
    f = good(); f["invoice_number"] = None
    codes = [e["code"] for e in validate(f, {k: 0.9 for k in f}, FakeDB(), 1)]
    assert "MISSING_FIELD" in codes

def test_negative_amount_flagged():
    f = good(); f["tax"] = -5.0
    codes = [e["code"] for e in validate(f, {k: 0.9 for k in f}, FakeDB(), 1)]
    assert "NEGATIVE_AMOUNT" in codes

def test_line_sum_mismatch_is_warning():
    f = good(); f["line_items"] = [{"description": "X", "quantity": 1, "unit_price": 10.0, "amount": 10.0}]
    errs = validate(f, {k: 0.9 for k in f}, FakeDB(), 1)
    assert any(e["code"] == "LINE_SUM_MISMATCH" and e["severity"] == "warning" for e in errs)

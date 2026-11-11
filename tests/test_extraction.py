import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.extract import extract_from_text, extract_from_table
from app.validate import validate

SAMPLE = """INVOICE
Invoice Number: INV-1042
Invoice Date: 2026-10-05
Supplier: Acme Supplies Ltd
Bill To: Northwind Retail
Widget A  2  25.00  50.00
Subtotal: $50.00
Tax: $5.00
Total: $55.00
Currency: USD
"""

def test_extracts_all_fields():
    f = extract_from_text(SAMPLE)["fields"]
    assert f["invoice_number"] == "INV-1042"
    assert f["invoice_date"] == "2026-10-05"
    assert f["supplier_name"] == "Acme Supplies Ltd"
    assert f["customer_name"] == "Northwind Retail"
    assert f["subtotal"] == 50.00 and f["tax"] == 5.00 and f["total"] == 55.00
    assert f["currency"] == "USD"
    assert f["line_items"][0]["description"] == "Widget A"

def test_missing_fields_are_null_not_invented():
    f = extract_from_text("Some random memo with no invoice data.")["fields"]
    assert f["invoice_number"] is None and f["total"] is None and f["supplier_name"] is None

def test_table_extraction():
    sheets = {"Items": [{"invoice_number": "INV-7", "invoice_date": "2026-10-01",
                         "supplier": "Globex", "customer": "Hooli",
                         "description": "Cable set", "quantity": "2",
                         "unit_price": "12.50", "amount": "25.00"},
                        {"invoice_number": "INV-7", "description": "Widget B",
                         "quantity": "1", "unit_price": "40.00", "amount": "40.00"}]}
    f = extract_from_table(sheets)["fields"]
    assert f["invoice_number"] == "INV-7" and f["supplier_name"] == "Globex"
    assert len(f["line_items"]) == 2

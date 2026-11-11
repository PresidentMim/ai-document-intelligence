"""Generate a labeled synthetic invoice dataset (no real company data).

20 invoices: 8 digital PDF, 4 scanned-style PDF (image-only PDF),
4 PNG images, 2 XLSX (multi-sheet), 2 CSV. Ground truth in
data/labeled/ground_truth.json. Two intentionally broken cases:
one TOTAL_MISMATCH and one missing invoice number — so validation
and the evaluation actually exercise the failure paths.
Usage: python3 scripts/generate_dataset.py
"""
import csv, json, random
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "data"
SAMPLES = OUT / "samples"; LABELED = OUT / "labeled"
SAMPLES.mkdir(parents=True, exist_ok=True); LABELED.mkdir(parents=True, exist_ok=True)

SUPPLIERS = ["Acme Supplies Ltd", "Globex Trading Co", "Initech Office Goods",
             "Umbrella Logistics", "Stark Industrial"]
CUSTOMERS = ["Northwind Retail", "Wayne Enterprises", "Hooli Corp",
             "Pied Piper Inc", "Massive Dynamic"]
ITEMS = [("Widget A", 25.00), ("Widget B", 40.00), ("Cable set", 12.50),
         ("Office chair", 120.00), ("Printer paper (ream)", 8.00), ("Monitor 24in", 150.00)]
random.seed(42)

def invoice_text(inv):
    lines = [f"INVOICE", f"Invoice Number: {inv['invoice_number']}",
             f"Invoice Date: {inv['invoice_date']}",
             f"Supplier: {inv['supplier_name']}", f"Bill To: {inv['customer_name']}",
             "", "Description  Qty  Unit Price  Amount"]
    for it in inv["line_items"]:
        lines.append(f"{it['description']}  {it['quantity']}  {it['unit_price']:.2f}  {it['amount']:.2f}")
    lines += ["", f"Subtotal: ${inv['subtotal']:.2f}", f"Tax: ${inv['tax']:.2f}",
              f"Total: ${inv['total']:.2f}", "Currency: USD"]
    return lines

def make_invoice(i):
    items = random.sample(ITEMS, k=random.randint(2, 3))
    line_items = []
    for name, price in items:
        q = random.randint(1, 5)
        line_items.append({"description": name, "quantity": q, "unit_price": price,
                           "amount": round(q * price, 2)})
    sub = round(sum(x["amount"] for x in line_items), 2)
    tax = round(sub * 0.10, 2)
    return {"invoice_number": f"INV-{1000+i}", "invoice_date": f"2026-10-{i+1:02d}",
            "supplier_name": SUPPLIERS[i % len(SUPPLIERS)],
            "customer_name": CUSTOMERS[i % len(CUSTOMERS)],
            "subtotal": sub, "tax": tax, "total": round(sub + tax, 2),
            "currency": "USD", "line_items": line_items}

def pdf_digital(inv, path):
    c = canvas.Canvas(str(path), pagesize=A4)
    y = 800
    for line in invoice_text(inv):
        c.drawString(60, y, line); y -= 18
    c.showPage(); c.save()

def image_invoice(inv, path, scanned_pdf=False):
    img = Image.new("RGB", (900, 1100), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except Exception:
        font = ImageFont.load_default()
    y = 40
    for line in invoice_text(inv):
        d.text((40, y), line, fill="black", font=font); y += 34
    if scanned_pdf:
        img.save(path.with_suffix(".tmp.png"))
        # image-only PDF = scanned document (no text layer)
        img.save(path, "PDF", resolution=200.0)
        path.with_suffix(".tmp.png").unlink(missing_ok=True)
    else:
        img.save(path)

def spreadsheet(inv, path, multi=True):
    import pandas as pd
    rows = [{"invoice_number": inv["invoice_number"], "invoice_date": inv["invoice_date"],
             "supplier": inv["supplier_name"], "customer": inv["customer_name"],
             "description": it["description"], "quantity": it["quantity"],
             "unit_price": it["unit_price"], "amount": it["amount"],
             "subtotal": inv["subtotal"], "tax": inv["tax"],
             "total": inv["total"], "currency": inv["currency"]}
            for it in inv["line_items"]]
    df = pd.DataFrame(rows)
    totals = pd.DataFrame([{"invoice_number": inv["invoice_number"], "subtotal": inv["subtotal"],
                            "tax": inv["tax"], "total": inv["total"], "currency": "USD"}])
    if path.suffix == ".csv":
        df.to_csv(path, index=False)
    else:
        with pd.ExcelWriter(path) as w:
            df.to_excel(w, sheet_name="Items", index=False)
            if multi:
                totals.to_excel(w, sheet_name="Totals", index=False)

def main():
    truth = {}
    for i in range(20):
        inv = make_invoice(i)
        # Intentional defects for validation testing
        if i == 17:  # total mismatch
            inv["total"] = round(inv["total"] + 50.00, 2)
        if i == 18:  # missing invoice number in the rendered doc (truth keeps it)
            rendered = dict(inv); rendered["invoice_number"] = ""
        else:
            rendered = inv
        if i < 8:
            p = SAMPLES / f"invoice_{i+1:02d}.pdf"; pdf_digital(rendered, p)
        elif i < 12:
            p = SAMPLES / f"invoice_{i+1:02d}_scanned.pdf"; image_invoice(rendered, p, scanned_pdf=True)
        elif i < 16:
            p = SAMPLES / f"invoice_{i+1:02d}.png"; image_invoice(rendered, p)
        elif i < 18:
            p = SAMPLES / f"invoice_{i+1:02d}.xlsx"; spreadsheet(rendered, p)
        else:
            p = SAMPLES / f"invoice_{i+1:02d}.csv"; spreadsheet(rendered, p)
        truth[p.name] = inv
    (LABELED / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(f"Generated 20 files in {SAMPLES}, truth in {LABELED/'ground_truth.json'}")

if __name__ == "__main__":
    main()

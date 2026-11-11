"""Evaluate the pipeline against data/labeled/ground_truth.json.

Runs the real ingest+extract+validate code (no API needed), times
each file, and reports per-field accuracy, document success rate,
failure rate, and mean processing time. Writes
evaluation/metrics.json — the numbers quoted in evaluation_report.md
must come from this file, not from memory.
Usage: python3 scripts/evaluate.py
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.extract import extract_from_text, extract_from_table
from app.ocr import extract_text
from app.spreadsheets import parse_spreadsheet

ROOT = Path(__file__).resolve().parent.parent
TRUTH = json.loads((ROOT / "data/labeled/ground_truth.json").read_text())
FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name",
          "subtotal", "tax", "total", "currency"]

def close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 0.01
    return str(a) == str(b)

def main():
    per_field = {f: {"correct": 0, "total": 0} for f in FIELDS}
    rows, ok_docs, failed = [], 0, []
    t_all = time.time()
    for name, truth in sorted(TRUTH.items()):
        p = ROOT / "data/samples" / name
        t0 = time.time()
        try:
            if p.suffix in {".xlsx", ".xls", ".csv"}:
                parsed = parse_spreadsheet(p)
                res = extract_from_table(parsed["sheets"])
            else:
                text, _, _, _ = extract_text(p)
                res = extract_from_text(text)
            fields = res["fields"]
            correct = sum(1 for f in FIELDS if close(fields.get(f), truth.get(f)))
            for f in FIELDS:
                per_field[f]["total"] += 1
                if close(fields.get(f), truth.get(f)):
                    per_field[f]["correct"] += 1
            ok_docs += (correct == len(FIELDS))
            rows.append({"file": name, "type": p.suffix, "fields_correct": f"{correct}/{len(FIELDS)}",
                         "seconds": round(time.time() - t0, 2)})
        except Exception as e:
            failed.append({"file": name, "error": str(e)[:200]})
            rows.append({"file": name, "type": p.suffix, "fields_correct": "ERROR",
                         "seconds": round(time.time() - t0, 2)})
    total = len(TRUTH)
    metrics = {
        "documents": total,
        "fully_correct_documents": ok_docs,
        "document_success_rate": round(ok_docs / total, 3),
        "failed_documents": len(failed),
        "failure_rate": round(len(failed) / total, 3),
        "mean_seconds_per_document": round((time.time() - t_all) / total, 2),
        "total_seconds": round(time.time() - t_all, 2),
        "per_field_accuracy": {f: round(v["correct"] / v["total"], 3) for f, v in per_field.items()},
        "mean_field_accuracy": round(sum(v["correct"] for v in per_field.values()) /
                                     sum(v["total"] for v in per_field.values()), 3),
        "rows": rows, "failures": failed,
    }
    out = ROOT / "evaluation" / "metrics.json"
    out.write_text(json.dumps(metrics, indent=2))
    print(json.dumps({k: v for k, v in metrics.items() if k not in ("rows",)}, indent=2))
    for r in rows:
        print(r)

if __name__ == "__main__":
    main()

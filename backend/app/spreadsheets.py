"""Spreadsheet / CSV parsing. Handles multi-sheet workbooks, header
detection (first row containing a known invoice column), empty sheets,
and corrupt files (clean ValueError). Returns normalised text (for
search + LLM) plus a row-oriented table for extraction."""
import csv, io
from pathlib import Path
import pandas as pd

KNOWN_COLS = {"invoice", "number", "date", "supplier", "customer", "subtotal",
              "tax", "total", "currency", "description", "item", "qty",
              "quantity", "unit", "price", "amount"}

def _norm_header(h):
    return str(h).strip().lower().replace(" ", "_")

def parse_spreadsheet(path: Path):
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            sheets = {"Sheet1": df}
        elif suffix in {".xlsx", ".xls"}:
            xls = pd.ExcelFile(path)
            sheets = {}
            for name in xls.sheet_names:
                try:
                    sheets[name] = pd.read_excel(xls, sheet_name=name, dtype=str,
                                                 keep_default_na=False)
                except Exception:
                    sheets[name] = pd.DataFrame()
        else:
            raise ValueError(f"not a spreadsheet: {suffix}")
    except Exception as e:
        raise ValueError(f"Could not parse spreadsheet ({suffix}): {e}") from e
    # Normalise headers, drop fully-empty sheets/rows
    clean = {}
    for name, df in sheets.items():
        df = df.copy()
        df.columns = [_norm_header(c) for c in df.columns]
        df = df.loc[:, ~df.columns.duplicated()]
        df = df[df.apply(lambda r: any(str(v).strip() for v in r), axis=1)]
        clean[name] = df
    text_parts = []
    for name, df in clean.items():
        text_parts.append(f"--- Sheet: {name} ({len(df)} rows) ---")
        text_parts.append(df.to_csv(index=False))
    return {"sheets": {k: v.to_dict("records") for k, v in clean.items()},
            "sheet_names": list(clean.keys()),
            "text": "\n".join(text_parts),
            "row_count": sum(len(v) for v in clean.values())}

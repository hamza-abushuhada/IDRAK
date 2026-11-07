import csv
import datetime as dt
import io

from openpyxl import load_workbook

MAX_ROWS = 20000


def read_table(filename: str, data: bytes, sheet: str | None = None) -> tuple[list[str], list[list], list[str]]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets = wb.sheetnames
        ws = wb[sheet] if sheet in sheets else wb[sheets[0]]
        it = ws.iter_rows(values_only=True)
        header_row = None
        rows = []
        for r in it:
            if header_row is None:
                if r and sum(1 for v in r if v not in (None, "")) >= 2:
                    header_row = r
                continue
            rows.append(list(r))
            if len(rows) >= MAX_ROWS:
                break
        wb.close()
        if header_row is None:
            return [], [], sheets
        headers = _headers(header_row)
    else:
        text = None
        for enc in ("utf-8-sig", "cp1256", "latin-1"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(text), dialect)
        all_rows = [r for r in reader]
        sheets = ["CSV"]
        while all_rows and sum(1 for v in all_rows[0] if v.strip()) < 2:
            all_rows.pop(0)
        if not all_rows:
            return [], [], sheets
        headers = _headers(all_rows[0])
        rows = [list(r) for r in all_rows[1:MAX_ROWS + 1]]
    width = len(headers)
    rows = [(r + [None] * width)[:width] for r in rows]
    while rows and all(v in (None, "") for v in rows[-1]):
        rows.pop()
    rows = [[_native(v) for v in r] for r in rows]
    return headers, rows, sheets


def _headers(row) -> list[str]:
    out, seen = [], {}
    for i, h in enumerate(row):
        h = str(h).strip() if h not in (None, "") else f"Column {i + 1}"
        if h in seen:
            seen[h] += 1
            h = f"{h} ({seen[h]})"
        else:
            seen[h] = 1
        out.append(h)
    while out and out[-1].startswith("Column "):
        out.pop()
    return out


def _native(v):
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    if isinstance(v, dt.date):
        return v.isoformat()
    return v

"""Read an uploaded table (CSV/TXT, XLSX/XLSM, old XLS, or any of them gzipped).

The format comes from the file's first bytes, not its name: a customer's file can
arrive as "export", "data.csv" holding an Excel workbook, or gzipped by the
browser on the way up. The name is only a fallback for plain text.
"""
import csv
import datetime as dt
import io
import re
import zlib

from openpyxl import load_workbook

# The most rows one file may hold (99,500 read, cleaned and imported locally in ~25 s; 300,000 cleaned in
# 49 s but recorded 1.15 million cell changes). Above it the upload is refused with the row
# count; it used to stop at 20,000 rows without a word, dropping the rest.
MAX_ROWS = 150_000
# The most a (decompressed) file may weigh. Guards the gzip path against a tiny
# upload that inflates into gigabytes.
MAX_BYTES = 200 * 1024 * 1024

_GZIP = b"\x1f\x8b"
_ZIP = b"PK\x03\x04"                          # .xlsx / .xlsm (a zip of XML)
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"    # .xls (Excel 97-2003)


class TooManyRows(ValueError):
    def __init__(self, rows: int):
        self.rows = rows
        super().__init__(f"{rows:,} rows")


class TooLarge(ValueError):
    pass


def gunzip(data: bytes, limit: int = MAX_BYTES) -> bytes:
    """Decompress gzip, refusing anything that inflates past `limit` bytes."""
    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out = d.decompress(data, limit + 1)
    if len(out) > limit or d.unconsumed_tail:
        raise TooLarge(f"The file is larger than {limit // (1024 * 1024)} MB once unpacked")
    return out + d.flush()


def file_format(filename: str, data: bytes) -> str:
    """"xlsx" | "xls" | "text", from the content; the name only decides nothing else fits."""
    if data[:4] == _ZIP:
        return "xlsx"
    if data[:8] == _OLE:
        return "xls"
    return "text"


def read_table(filename: str, data: bytes, sheet: str | None = None,
               max_rows: int = MAX_ROWS, cut: bool = False) -> tuple[list[str], list[list], list[str]]:
    """(headers, rows, sheet names). More than max_rows rows raises TooManyRows,
    unless cut=True (a quick preview) keeps the first max_rows."""
    if data[:2] == _GZIP:
        data = gunzip(data)
    fmt = file_format(filename, data)
    if fmt == "xlsx":
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets = wb.sheetnames
        ws = wb[sheet] if sheet in sheets else wb[sheets[0]]
        grid = _take(ws.iter_rows(values_only=True), max_rows, cut)
        wb.close()
    elif fmt == "xls":
        grid, sheets = _read_xls(data, sheet, max_rows, cut)
    else:
        text = _decode(data)
        try:
            dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        grid = _take(csv.reader(io.StringIO(text), dialect), max_rows, cut)
        sheets = ["CSV"]
    headers, rows = _split_header(grid)
    if not headers:
        return [], [], sheets
    width = len(headers)
    rows = [(r + [None] * width)[:width] for r in rows]
    while rows and all(v in (None, "") for v in rows[-1]):
        rows.pop()
    rows = [[_native(v) for v in r] for r in rows]
    return headers, rows, sheets


_NOT_TABLES = (b"%PDF", b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"Rar!", b"7z\xbc\xaf")


def _decode(data: bytes) -> str:
    # Excel's "Unicode text" export (common for Arabic sheets) is UTF-16 with a BOM.
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    if data.startswith(_NOT_TABLES) or b"\x00" in data[:4096]:
        raise ValueError("this isn't a CSV or Excel file")
    for enc in ("utf-8-sig", "cp1256"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _take(it, max_rows: int, cut: bool) -> list[list]:
    """The header row plus up to max_rows data rows (leading blank lines skipped)."""
    out: list[list] = []
    for r in it:
        r = list(r)
        if not out and sum(1 for v in r if v not in (None, "") and str(v).strip()) < 2:
            continue  # title lines and blank lines above the table
        if len(out) == max_rows + 1:  # the header and max_rows rows are in; r is one too many
            if cut:
                break
            raise TooManyRows(max_rows + 1 + sum(1 for _ in it))
        out.append(r)
    return out


def _read_xls(data: bytes, sheet: str | None, max_rows: int, cut: bool) -> tuple[list[list], list[str]]:
    import xlrd  # Excel 97-2003; only loaded for those files

    book = xlrd.open_workbook(file_contents=data, on_demand=True)
    sheets = book.sheet_names()
    sh = book.sheet_by_name(sheet) if sheet in sheets else book.sheet_by_index(0)

    def cell(c):
        if c.ctype == xlrd.XL_CELL_DATE:
            try:
                return xlrd.xldate_as_datetime(c.value, book.datemode)
            except (ValueError, OverflowError):
                return c.value
        if c.ctype == xlrd.XL_CELL_NUMBER and float(c.value).is_integer():
            return int(c.value)
        if c.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
            return None
        return c.value

    grid = _take(([cell(c) for c in sh.row(rx)] for rx in range(sh.nrows)), max_rows, cut)
    book.release_resources()
    return grid, sheets


# ── Is the first row names or already data? ────────────────────────────────────
_NUMBER = re.compile(r"^[-+]?[\d٠-٩,]*[.٫]?[\d٠-٩]+$")
_DATE = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}")


def _is_value(v) -> bool:
    if isinstance(v, (int, float, dt.date)):
        return True
    s = str(v or "").strip()
    return bool(s) and bool(_NUMBER.match(s.replace(" ", "")) or _DATE.match(s))


def _year(v) -> bool:
    s = str(v or "").strip()
    return s.isdigit() and 1990 <= int(s) <= 2100


def _headerless(first: list, sample: list[list]) -> bool:
    """A file exported without a header row: in every column whose values are numbers
    or dates, the first row holds a number or date too. Names never do, except a
    year as a column name ("2024"), which only counts when the column holds years."""
    from .fields import guess_field  # fields imports nothing from here

    if any(guess_field(str(v))[1] >= 1.0 for v in first if v not in (None, "")):
        return False  # a known column name ("Date", "الكمية")
    typed = agree = 0
    for ci, v in enumerate(first):
        col = [r[ci] for r in sample if ci < len(r) and r[ci] not in (None, "")]
        if len(col) < 3 or sum(_is_value(x) for x in col) < 0.8 * len(col):
            continue
        typed += 1
        if _is_value(v) and not (_year(v) and not all(_year(x) for x in col)):
            agree += 1
    return typed > 0 and agree == typed


def _split_header(grid: list[list]) -> tuple[list[str], list[list]]:
    if not grid:
        return [], []
    first, rest = grid[0], grid[1:]
    if _headerless(first, rest[:200]):
        width = max(len(r) for r in grid[:200])
        while width and all(len(r) < width or r[width - 1] in (None, "") for r in grid[:200]):
            width -= 1
        return [f"Column {i + 1}" for i in range(width)], grid
    return _headers(first), rest


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

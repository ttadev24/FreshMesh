"""A store's sales file from its POS (KiotViet, Sapo or any CSV export) → a preview; nothing is written to the
chain DB. The preview says which rows were understood, how they compare with the sales FreshMesh holds, and,
for days after the data, how FreshMesh's own forecast did against the real sales (P10–P90 coverage). Saving
an import would be a draft a person approves (not offered yet).

Columns are found by name, accent- and case-insensitive (``Ngày``, ``Mã hàng``, ``Tên hàng``, ``Số lượng``…);
dates ``dd/mm/yyyy`` (optional time), ``yyyy-mm-dd`` or ``dd-mm-yyyy``. Products are matched by FreshMesh code,
else by name."""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass

from api.errors import ApiError

MAX_CHARS = 1_000_000
MAX_ROWS = 20_000
ALIASES = {
    "date": ("ngay", "ngay_ban", "ngay_chung_tu", "ngay_hoa_don", "thoi_gian", "date"),
    "sku": ("ma_hang", "ma_hang_hoa", "ma_sp", "ma_san_pham", "sku", "sku_id"),
    "name": ("ten_hang", "ten_hang_hoa", "ten_san_pham", "ten_sp", "san_pham", "name", "product"),
    "qty": ("so_luong", "so_luong_ban", "sl", "sl_ban", "qty", "quantity"),
}
_DATE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})|^(\d{4})-(\d{2})-(\d{2})")


def key(text: str) -> str:
    """'Số lượng' -> 'so_luong': accent-free, lower case, underscores."""
    plain = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in plain if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "_", plain).strip("_")


def _date(text: str) -> dt.date | None:
    m = _DATE.match(text.strip())
    if not m:
        return None
    d, mo, y = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(5), m.group(4))
    try:
        return dt.date(int(y), int(mo), int(d))
    except ValueError:
        return None


def _qty(text: str) -> float | None:
    t = text.strip().replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", t):  # Vietnamese thousands: 1.200
        t = t.replace(".", "")
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


@dataclass(frozen=True)
class Parsed:
    totals: dict[tuple[str, dt.date], float]  # (sku_id, day) -> units
    rows_read: int
    issues_vi: list[str]
    unknown_products: list[str]


def parse_sales(text: str, skus: dict[str, str]) -> Parsed:
    """``skus``: FreshMesh sku_id -> name. Raises 422 when the file cannot be read as a sales export."""
    if len(text) > MAX_CHARS:
        raise ApiError(413, "sales_file_too_large", "File bán hàng tối đa 1 MB; hãy xuất theo từng tuần.")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text.lstrip("﻿")), dialect)
    header = next(reader, [])
    cols = {k: next((i for i, h in enumerate(header) if key(h) in names), None) for k, names in ALIASES.items()}
    if cols["date"] is None or cols["qty"] is None or (cols["sku"] is None and cols["name"] is None):
        raise ApiError(422, "bad_sales_file", "Không nhận ra cột của file. Cần cột Ngày, Số lượng và Mã hàng "
                       "hoặc Tên hàng (ví dụ file xuất 'Hàng hóa bán ra' của KiotViet/Sapo).")  # fmt: skip
    by_code = {key(s): s for s in skus}
    by_name = {key(n): s for s, n in skus.items()}
    totals: dict[tuple[str, dt.date], float] = defaultdict(float)
    issues: list[str] = []
    unknown: set[str] = set()
    n = 0
    for n, row in enumerate(reader, start=1):
        if n > MAX_ROWS:
            raise ApiError(413, "sales_file_too_large", f"File bán hàng tối đa {MAX_ROWS} dòng.")
        cell = {k: row[c] if c is not None and c < len(row) else "" for k, c in cols.items()}
        day, qty = _date(cell["date"]), _qty(cell["qty"])
        code, name = cell["sku"], cell["name"]
        sku = by_code.get(key(code)) or by_name.get(key(name))
        if day is None or qty is None:
            if len(issues) < 10:
                issues.append(f"Dòng {n + 1}: không đọc được ngày hoặc số lượng.")
            continue
        if sku is None:
            unknown.add(name or code or "?")
            continue
        totals[(sku, day)] += qty
    return Parsed(dict(totals), n, issues, sorted(unknown)[:20])

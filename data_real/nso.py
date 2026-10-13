"""HCMC retail trade & service revenue by year (NSO/GSO statistics, compiled on Hugging Face).

Reference only: the per-year provincial aggregate is reported next to the generated demand level in
docs/data-provenance.md; it is not written into the chain DBs and does not tune any parameter.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from data_real.net import PoliteClient, raw_refs, save_raw, utc_now_iso

DATASET_ID = "NSO_HCMC_RETAIL_REF"
REPO = "letrinhan/vn-provinces-trade-tourism-transport-master"
CSV_URL = f"https://huggingface.co/datasets/{REPO}/resolve/main/data/provinces.csv"
CARD_URL = f"https://huggingface.co/datasets/{REPO}/resolve/main/README.md"
LICENSE = "HF card: license 'other' (no terms stated); underlying figures: NSO/GSO published statistics"
COLUMNS = ("retail_trade_and_service_revenue", "markets", "supermarkets", "shopping_centers")


def parse_hcmc(text: str) -> list[dict[str, Any]]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        if r["geo_short"] != "HCM":
            continue
        rows.append({"year": int(r["year"]), **{c: (float(r[c]) if r[c] else None) for c in COLUMNS}})
    return sorted(rows, key=lambda r: r["year"])


def fetch_nso(data_dir: Path, client: PoliteClient, snapshot_path: Path, log=print) -> dict[str, Any]:
    card = client.get(CARD_URL)
    when = utc_now_iso()
    save_raw(
        data_dir,
        "nso/README.md",
        card.content,
        url=CARD_URL,
        retrieved_at=when,
        license=LICENSE,
        dataset_id=DATASET_ID,
    )
    resp = client.get(CSV_URL)
    save_raw(
        data_dir,
        "nso/provinces.csv",
        resp.content,
        url=CSV_URL,
        retrieved_at=when,
        license=LICENSE,
        dataset_id=DATASET_ID,
    )
    rows = parse_hcmc(resp.text)
    card_license = next(
        (
            ln.split(":", 1)[1].strip().strip('"')
            for ln in card.text.splitlines()
            if ln.startswith("license:")
        ),
        None,
    )
    meta = {
        "dataset_id": DATASET_ID,
        "url": CSV_URL,
        "card_license": card_license,
        "license": LICENSE,
        "retrieved_at": when,
        "unit_revenue": "tỷ đồng, giá hiện hành (quy ước niên giám NSO; bảng nguồn không ghi đơn vị)",
        "geo": "Ho Chi Minh City (63-tỉnh cũ)",
        "years": [rows[0]["year"], rows[-1]["year"]] if rows else [],
        "raw_files": raw_refs(data_dir, (DATASET_ID,)),
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    log(f"  NSO/GSO HCMC: {len(rows)} năm, giấy phép thẻ HF = {card_license!r}")
    return meta

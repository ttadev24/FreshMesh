import pytest

from api.errors import ApiError
from api.sales_import import key, parse_sales
from tests.api.conftest import assert_error

SKUS = {"SKU_RAU_MUONG": "Rau muống (bó 500g)", "SKU_CA_CHUA": "Cà chua (kg)"}


def test_kiotviet_like_export_is_read_by_column_name_and_product_name():
    text = (
        "﻿Ngày;Mã hàng;Tên hàng;Số lượng\n"
        "30/09/2026 08:15;SP0001;Rau muống (bó 500g);12\n"
        "30/09/2026 17:40;SP0001;RAU MUONG (BO 500G);3\n"
        "2026-09-29;SKU_CA_CHUA;;0.500\n"
        "hôm qua;SP0001;Rau muống (bó 500g);4\n"
        "30/09/2026;SP9;Bánh mì;2\n"
    )
    out = parse_sales(text, SKUS)
    import datetime as dt

    assert out.totals == {("SKU_RAU_MUONG", dt.date(2026, 9, 30)): 15.0, ("SKU_CA_CHUA", dt.date(2026, 9, 29)): 0.5}
    assert out.rows_read == 5 and out.unknown_products == ["Bánh mì"] and "Dòng 5" in out.issues_vi[0]
    assert key("Số lượng bán") == "so_luong_ban" and key("Đơn vị") == "don_vi"


def test_a_file_without_the_needed_columns_is_refused_in_vietnamese():
    with pytest.raises(ApiError) as exc:
        parse_sales("a,b,c\n1,2,3\n", SKUS)
    assert exc.value.code == "bad_sales_file" and "Số lượng" in exc.value.message_vi


def test_sample_file_round_trips_and_checks_the_forecast(client, owner_a):
    r = client.get("/api/sales/import/sample?store_id=A-CH1", headers=owner_a)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    text = r.text
    assert text.startswith("Ngày,Mã hàng,Tên hàng,Số lượng") and "01/10/2026" in text
    out = client.post("/api/sales/import/preview", json={"store_id": "A-CH1", "csv_text": text},
                      headers=owner_a).json()  # fmt: skip
    assert out["saved"] is False and out["unknown_products"] == [] and out["compared"] > 0
    assert out["differences"] == []  # the 6 days from the chain DB match exactly
    assert out["forecast_check"] and all(c["date"] == "2026-10-01" for c in out["forecast_check"])
    assert out["forecast_coverage_pct"] is not None and "P10–P90" in out["summary_vi"]


def test_manager_cannot_preview_another_store(client, manager_a):
    body = {"store_id": "A-CH3", "csv_text": "Ngày,Mã hàng,Số lượng\n30/09/2026,SKU_RAU_MUONG,1\n"}
    assert_error(client.post("/api/sales/import/preview", json=body, headers=manager_a), 403)


def test_quantities_follow_the_files_decimal_convention_and_reject_non_finite_values():
    import datetime as dt

    vn = parse_sales("Ngày;Mã hàng;Số lượng\n29/09/2026;SKU_CA_CHUA;1.234,5\n30/09/2026;SKU_CA_CHUA;0,5\n", SKUS)
    assert vn.totals == {("SKU_CA_CHUA", dt.date(2026, 9, 29)): 1234.5, ("SKU_CA_CHUA", dt.date(2026, 9, 30)): 0.5}
    bad = parse_sales("Ngày,Mã hàng,Số lượng\n29/09/2026,SKU_CA_CHUA,nan\n30/09/2026,SKU_CA_CHUA,1e400\n"
                      "15/10/20261,SKU_CA_CHUA,2\n", SKUS)  # fmt: skip
    assert bad.totals == {} and len(bad.issues_vi) == 3


def test_broken_csv_is_a_422_not_a_crash():
    unclosed = 'Ngày,Mã hàng,Số lượng\n30/09/2026,"SKU_CA_CHUA,1\n'
    too_long = "Ngày,Mã hàng,Số lượng\n30/09/2026,SKU_CA_CHUA," + "1" * 200_000 + "\n"
    assert parse_sales(unclosed, SKUS).totals == {}  # the rest of the file is one cell: flagged, no crash
    with pytest.raises(ApiError) as exc:
        parse_sales(too_long, SKUS)
    assert exc.value.status == 422 and exc.value.code == "bad_sales_file"


def test_classic_mac_line_endings_are_read():
    out = parse_sales("Ngày,Mã hàng,Số lượng\r30/09/2026,SKU_CA_CHUA,2\r", SKUS)
    assert sum(out.totals.values()) == 2.0

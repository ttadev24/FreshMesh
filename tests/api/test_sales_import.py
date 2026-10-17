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
        "2026-09-29;SKU_CA_CHUA;;1.200\n"
        "hôm qua;SP0001;Rau muống (bó 500g);4\n"
        "30/09/2026;SP9;Bánh mì;2\n"
    )
    out = parse_sales(text, SKUS)
    import datetime as dt

    assert out.totals == {("SKU_RAU_MUONG", dt.date(2026, 9, 30)): 15.0, ("SKU_CA_CHUA", dt.date(2026, 9, 29)): 1200.0}
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

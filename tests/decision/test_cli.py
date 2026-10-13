import pytest

from decision.cli import main
from tests.api.helpers import build_data


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    return build_data(tmp_path_factory.mktemp("cli_data"))


def test_flow1_prints_three_plans_in_vietnamese(data_dir, capsys):
    rc = main(
        ["flow1", "--chain", "CHAIN_A", "--store", "A-CH1", "--items", "rau,thit", "--data", str(data_dir)]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "SIMULATED" not in out
    # provenance line built from the datasets of the tables actually used (fixture registry labels)
    assert "Nguồn dữ liệu: " in out and "Bộ bán hàng thử nghiệm" in out and "Lịch thử nghiệm" in out
    assert "P10 / P50 / P90" in out
    for label in ("Phương án An toàn", "Phương án Cân bằng", "Phương án Tiết kiệm"):
        assert label in out
    assert "dự kiến bỏ" in out and "hết hàng" in out and " đ" in out
    assert "Độ tin cậy:" in out and "Giả định:" in out and "Việc cần bạn duyệt" in out
    assert "Rau muống" in out and "Thịt heo ba rọi" in out


def test_flow1_unknown_store_is_a_vietnamese_error(data_dir, capsys):
    rc = main(["flow1", "--chain", "CHAIN_A", "--store", "CH42", "--data", str(data_dir)])
    assert rc == 1
    assert "Cửa hàng" in capsys.readouterr().err

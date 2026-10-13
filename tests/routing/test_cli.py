import json
from pathlib import Path

from routing.cli import batch_from_dict, main
from routing.client import SolverError, SolverResponse
from routing.models import DeliveryMode

EXAMPLE = Path(__file__).resolve().parents[2] / "routing" / "examples" / "batch_q7.json"


def test_batch_from_dict_parses_modes_and_points():
    batch = batch_from_dict(json.loads(EXAMPLE.read_text()))
    assert batch.store.store_id == "Q7-01"
    assert len(batch.orders) == 12
    assert batch.orders[1].mode == DeliveryMode.PICKUP
    assert batch.orders[1].pickup_point_id == "PP-SKYGARDEN"
    assert batch.orders[2].mode == DeliveryMode.FLEXIBLE
    assert [p.point_id for p in batch.pickup_points] == ["PP-SKYGARDEN", "PP-HUNGVUONG"]


class EchoSolver:
    """Returns one route visiting every customer in input order (always consistent)."""

    def __init__(self, url, **_):
        pass

    def solve(self, instance_text, solver="paco", size="small"):
        lines = instance_text.splitlines()
        n, m = map(int, lines[0].split())
        matrix = lines[-n:] if m else []
        tokens, nodes = ["0"], []
        for c in range(1, n + 1):
            ctype = int(lines[2 + n + c].split()[5])
            row = matrix[c - 1].split()
            if ctype == 2:
                node = n + 1 + row.index("1")
                tokens.append(f"{c}({node})")
            else:
                node = c
                tokens.append(str(c))
            nodes.append(node)
        tokens.append("0")
        return SolverResponse(30.0, 1, 0.2, [tokens], [], nodes)


class BrokenSolver:
    def __init__(self, url, **_):
        pass

    def solve(self, *a, **k):
        raise SolverError("cannot reach solver: refused")


def test_main_prints_vietnamese_summary(capsys):
    code = main([str(EXAMPLE)], client_factory=EchoSolver)
    out = capsys.readouterr().out
    assert code == 0
    assert "SIMULATED" in out
    assert "Quãng đường ước tính" in out
    assert "mỗi đơn một chuyến" in out
    assert "D012" in out and "Đơn có nguy cơ" in out


def test_main_json_output(capsys):
    code = main([str(EXAMPLE), "--json"], client_factory=EchoSolver)
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["plan"]["source"] == "SIMULATED"
    assert data["baseline"]["trips"] == 11


def test_main_solver_failure_exits_2_without_route(capsys):
    code = main([str(EXAMPLE)], client_factory=BrokenSolver)
    captured = capsys.readouterr()
    assert code == 2
    assert "Không gọi được solver" in captured.err
    assert "Xe 1" not in captured.out


def test_main_bad_input_exits_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert main([str(bad)], client_factory=EchoSolver) == 1
    assert "Dữ liệu đợt đơn không hợp lệ" in capsys.readouterr().err

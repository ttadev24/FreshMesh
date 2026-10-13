import pytest

from data_sim import generate_all


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("sim42")
    generate_all(out, seed=42)
    return out

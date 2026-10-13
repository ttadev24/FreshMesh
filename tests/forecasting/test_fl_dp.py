import math

import pytest

from forecasting.fl.dp import DEFAULT_DELTA, noise_multiplier_for_epsilon, zcdp_epsilon


@pytest.mark.parametrize("eps", [0.5, 1.0, 10.0, 1000.0])
@pytest.mark.parametrize("rounds", [1, 20])
def test_epsilon_round_trip(eps, rounds):
    z = noise_multiplier_for_epsilon(eps, rounds)
    assert zcdp_epsilon(z, rounds) == pytest.approx(eps, rel=1e-9)


def test_known_value_single_round():
    # rho = 1 / (2 z^2) = 0.5 for z = 1; eps = rho + 2 sqrt(rho ln(1/delta))
    rho = 0.5
    expected = rho + 2 * math.sqrt(rho * math.log(1 / DEFAULT_DELTA))
    assert zcdp_epsilon(1.0, 1) == pytest.approx(expected)


def test_monotonicity():
    assert zcdp_epsilon(1.0, 40) > zcdp_epsilon(1.0, 20)  # composition: more rounds, more privacy loss
    assert zcdp_epsilon(2.0, 20) < zcdp_epsilon(1.0, 20)  # more noise, less privacy loss
    assert noise_multiplier_for_epsilon(1.0, 20) > noise_multiplier_for_epsilon(10.0, 20)


def test_edge_cases():
    assert zcdp_epsilon(0.0, 5) == math.inf
    with pytest.raises(ValueError):
        noise_multiplier_for_epsilon(0.0, 10)
    with pytest.raises(ValueError):
        noise_multiplier_for_epsilon(1.0, 0)
    with pytest.raises(ValueError):
        zcdp_epsilon(1.0, 5, delta=1.5)

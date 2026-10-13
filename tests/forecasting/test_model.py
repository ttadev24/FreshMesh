import numpy as np
import pytest

from forecasting.model import QuantileMLP


def _tiny(seed: int = 0) -> tuple[QuantileMLP, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    model = QuantileMLP(5, 4, emb_dim=2, hidden=(6, 4), seed=seed, dtype=np.float64)
    X = rng.normal(size=(12, 5))
    sku = rng.integers(0, 4, size=12)
    y = rng.normal(size=12) * 2 + 1
    return model, X, sku, y


def test_gradients_match_finite_differences():
    model, X, sku, y = _tiny()
    w_sample = np.abs(np.random.default_rng(1).normal(size=len(y))) + 0.5
    for sample_weight in (None, w_sample):
        _, grads = model.gradients(X, sku, y, sample_weight)
        weights = model.get_weights()
        eps = 1e-6
        for j, w in enumerate(weights):
            num = np.zeros_like(w)
            for idx in np.ndindex(w.shape):
                for sign in (1, -1):
                    pert = [x.copy() for x in weights]
                    pert[j][idx] += sign * eps
                    model.set_weights(pert)
                    num[idx] += sign * model.loss(X, sku, y, sample_weight) / (2 * eps)
            model.set_weights(weights)
            np.testing.assert_allclose(grads[j], num, rtol=1e-4, atol=1e-7, err_msg=f"weight {j}")


def test_predict_is_monotone_even_with_extreme_weights():
    model, X, sku, _ = _tiny()
    weights = model.get_weights()
    weights[-1] = np.array([3.0, -50.0, -50.0])
    weights[-2] = weights[-2] * 25
    model.set_weights(weights)
    q = model.predict(X * 10, sku)
    assert q.shape == (12, 3)
    assert np.all(np.diff(q, axis=1) >= 0)


def test_weights_roundtrip_and_shape_check():
    model, X, sku, _ = _tiny()
    w = model.get_weights()
    assert w[0].shape == (4, 2)  # SKU embedding table is the first weight array
    other = QuantileMLP(5, 4, emb_dim=2, hidden=(6, 4), seed=99, dtype=np.float64)
    other.set_weights(w)
    np.testing.assert_array_equal(other.predict(X, sku), model.predict(X, sku))
    with pytest.raises(ValueError):
        other.set_weights(w[:-1])
    with pytest.raises(ValueError):
        other.set_weights([np.zeros((3, 3))] + w[1:])


def test_fit_is_deterministic_and_learns_quantiles():
    rng = np.random.default_rng(3)
    n = 6000
    X = rng.normal(size=(n, 3))
    sku = rng.integers(0, 8, size=n)
    y = 2.0 + X[:, 0] + (0.5 + 0.5 * np.abs(X[:, 1])) * rng.normal(size=n)

    def train(seed):
        m = QuantileMLP(3, 8, hidden=(32, 16), seed=seed)
        hist = m.fit(X, sku, y, epochs=15, batch_size=256, lr=3e-3, seed=seed)
        return m, hist

    m1, h1 = train(0)
    m2, _ = train(0)
    for a, b in zip(m1.get_weights(), m2.get_weights(), strict=True):
        np.testing.assert_array_equal(a, b)
    assert h1[-1] < h1[0]

    Xt = rng.normal(size=(4000, 3))
    yt = 2.0 + Xt[:, 0] + (0.5 + 0.5 * np.abs(Xt[:, 1])) * rng.normal(size=4000)
    q = m1.predict(Xt, rng.integers(0, 8, size=4000))
    assert abs(np.mean(yt <= q[:, 0]) - 0.1) < 0.05
    assert abs(np.mean(yt <= q[:, 1]) - 0.5) < 0.06
    assert abs(np.mean(yt <= q[:, 2]) - 0.9) < 0.05

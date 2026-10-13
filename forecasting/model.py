"""Quantile MLP (P10/P50/P90) in pure numpy: pinball loss, manual backprop, Adam.

Architecture: ``[x, E[sku]] -> Dense+ReLU -> ... -> Dense(3)``. The three raw outputs ``z`` are mapped to
monotone quantiles with a cumulative-softplus head::

    q10 = z0,  q50 = q10 + softplus(z1),  q90 = q50 + softplus(z2)

so ``q10 <= q50 <= q90`` holds by construction. ``get_weights()`` returns
``[E, W1, b1, ..., Wout, bout]`` (embedding table first) — the order FedAvg/FedPer code relies on.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

QUANTILES = (0.1, 0.5, 0.9)


def _softplus(z: np.ndarray) -> np.ndarray:
    return np.logaddexp(0.0, z)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.tanh(0.5 * z))


class QuantileMLP:
    def __init__(
        self,
        n_features: int,
        n_sku_buckets: int,
        *,
        emb_dim: int = 4,
        hidden: Sequence[int] = (64, 32),
        seed: int = 0,
        dtype: type = np.float32,
    ) -> None:
        self.n_features = n_features
        self.n_sku_buckets = n_sku_buckets
        self.emb_dim = emb_dim
        self.hidden = tuple(hidden)
        self.dtype = np.dtype(dtype)
        self.taus = np.array(QUANTILES, dtype=self.dtype)
        rng = np.random.default_rng(seed)
        weights = [(rng.normal(0.0, 0.1, size=(n_sku_buckets, emb_dim)))]
        fan_in = n_features + emb_dim
        for width in self.hidden:
            weights.append(rng.normal(0.0, np.sqrt(2.0 / fan_in), size=(fan_in, width)))
            weights.append(np.zeros(width))
            fan_in = width
        weights.append(rng.normal(0.0, np.sqrt(1.0 / fan_in), size=(fan_in, 3)))
        # Bias so the initial head is roughly (0.5, 1, 1.5) in scaled units.
        weights.append(np.array([0.5, np.log(np.expm1(0.5)), np.log(np.expm1(0.5))]))
        self._w = [np.asarray(w, dtype=self.dtype) for w in weights]

    # --- weights ---------------------------------------------------------------------------------------
    def get_weights(self) -> list[np.ndarray]:
        return [w.copy() for w in self._w]

    def set_weights(self, weights: Sequence[np.ndarray]) -> None:
        if len(weights) != len(self._w):
            raise ValueError(f"expected {len(self._w)} weight arrays, got {len(weights)}")
        new = []
        for cur, w in zip(self._w, weights, strict=True):
            arr = np.asarray(w, dtype=self.dtype)
            if arr.shape != cur.shape:
                raise ValueError(f"weight shape mismatch: expected {cur.shape}, got {arr.shape}")
            new.append(arr.copy())
        self._w = new

    # --- forward/backward ------------------------------------------------------------------------------
    def _forward(self, X: np.ndarray, sku: np.ndarray) -> tuple[np.ndarray, list[np.ndarray], np.ndarray]:
        emb = self._w[0]
        a = np.concatenate([np.asarray(X, dtype=self.dtype), emb[sku]], axis=1)
        acts = [a]
        n_hidden = len(self.hidden)
        for i in range(n_hidden):
            W, b = self._w[1 + 2 * i], self._w[2 + 2 * i]
            a = np.maximum(a @ W + b, 0.0)
            acts.append(a)
        z = a @ self._w[-2] + self._w[-1]
        q = np.empty_like(z)
        q[:, 0] = z[:, 0]
        q[:, 1] = q[:, 0] + _softplus(z[:, 1])
        q[:, 2] = q[:, 1] + _softplus(z[:, 2])
        return q, acts, z

    def predict(self, X: np.ndarray, sku: np.ndarray) -> np.ndarray:
        """Return ``(n, 3)`` monotone quantiles (P10, P50, P90) in the model's target space."""
        q, _, _ = self._forward(X, np.asarray(sku, dtype=np.int64))
        return q

    def loss(
        self, X: np.ndarray, sku: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None
    ) -> float:
        q, _, _ = self._forward(X, np.asarray(sku, dtype=np.int64))
        return float(self._pinball(q, np.asarray(y, dtype=self.dtype), sample_weight))

    def _pinball(self, q: np.ndarray, y: np.ndarray, w: np.ndarray | None) -> np.ndarray:
        u = y[:, None] - q
        per = np.maximum(self.taus * u, (self.taus - 1.0) * u).mean(axis=1)
        if w is not None:
            per = per * w
        return per.mean()

    def gradients(
        self, X: np.ndarray, sku: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None
    ) -> tuple[float, list[np.ndarray]]:
        """Mean pinball loss (averaged over the 3 quantiles) and its gradient w.r.t. every weight array."""
        sku = np.asarray(sku, dtype=np.int64)
        y = np.asarray(y, dtype=self.dtype)
        q, acts, z = self._forward(X, sku)
        n = len(y)
        loss = float(self._pinball(q, y, sample_weight))
        u = y[:, None] - q
        g_q = np.where(u > 0, -self.taus, 1.0 - self.taus) / (3.0 * n)
        if sample_weight is not None:
            g_q = g_q * np.asarray(sample_weight, dtype=self.dtype)[:, None]
        g_z = np.empty_like(z)
        g_z[:, 0] = g_q.sum(axis=1)
        g_z[:, 1] = (g_q[:, 1] + g_q[:, 2]) * _sigmoid(z[:, 1])
        g_z[:, 2] = g_q[:, 2] * _sigmoid(z[:, 2])

        grads: list[np.ndarray] = [np.zeros_like(w) for w in self._w]
        grads[-2] = acts[-1].T @ g_z
        grads[-1] = g_z.sum(axis=0)
        g_a = g_z @ self._w[-2].T
        for i in reversed(range(len(self.hidden))):
            g_pre = g_a * (acts[i + 1] > 0)
            grads[1 + 2 * i] = acts[i].T @ g_pre
            grads[2 + 2 * i] = g_pre.sum(axis=0)
            g_a = g_pre @ self._w[1 + 2 * i].T
        g_emb = g_a[:, self.n_features :]
        np.add.at(grads[0], sku, g_emb)
        return loss, grads

    # --- training --------------------------------------------------------------------------------------
    def fit(
        self,
        X: np.ndarray,
        sku: np.ndarray,
        y: np.ndarray,
        *,
        epochs: int = 20,
        batch_size: int = 1024,
        lr: float = 2e-3,
        weight_decay: float = 1e-5,
        sample_weight: np.ndarray | None = None,
        seed: int = 0,
    ) -> list[float]:
        """Adam on minibatches; returns the mean training loss per epoch. Deterministic given ``seed``."""
        X = np.asarray(X, dtype=self.dtype)
        sku = np.asarray(sku, dtype=np.int64)
        y = np.asarray(y, dtype=self.dtype)
        w_all = None if sample_weight is None else np.asarray(sample_weight, dtype=self.dtype)
        rng = np.random.default_rng(seed)
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        m = [np.zeros_like(w) for w in self._w]
        v = [np.zeros_like(w) for w in self._w]
        step = 0
        n = len(y)
        history = []
        for epoch in range(epochs):
            lr_t = lr * 0.5 * (1.0 + np.cos(np.pi * epoch / max(epochs, 1)))
            order = rng.permutation(n)
            total = 0.0
            for start in range(0, n, batch_size):
                idx = order[start : start + batch_size]
                bw = None if w_all is None else w_all[idx]
                loss, grads = self.gradients(X[idx], sku[idx], y[idx], bw)
                total += loss * len(idx)
                step += 1
                c1 = 1.0 - beta1**step
                c2 = 1.0 - beta2**step
                for j, g in enumerate(grads):
                    if weight_decay and self._w[j].ndim == 2:
                        g = g + weight_decay * self._w[j]
                    m[j] = beta1 * m[j] + (1 - beta1) * g
                    v[j] = beta2 * v[j] + (1 - beta2) * g * g
                    self._w[j] = (self._w[j] - lr_t * (m[j] / c1) / (np.sqrt(v[j] / c2) + eps)).astype(
                        self.dtype
                    )
            history.append(total / max(n, 1))
        return history

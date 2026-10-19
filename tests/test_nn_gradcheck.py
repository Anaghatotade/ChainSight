"""Tests for the from-scratch NumPy neural network."""
import numpy as np
import pytest

import nn_numpy


def _data(n=24, d=5, seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(size=(n, d)), rng.normal(size=n)


def _randomise_biases(net, seed=1):
    # With all-zero biases a ReLU unit can sit EXACTLY on its kink (z = 0) where the derivative is undefined,
    # which makes the numerical gradient disagree with backprop. Non-zero biases avoid that artefact.
    rng = np.random.default_rng(seed)
    net.b = [rng.normal(0, 0.1, size=b.shape) for b in net.b]


@pytest.mark.parametrize("hidden", [(4, 3), (6,), ()])
def test_gradient_check_with_l2(hidden):
    X, y = _data()
    net = nn_numpy.NumpyMLP(5, hidden=hidden, l2=0.01, seed=3)
    _randomise_biases(net)
    assert net.gradient_check(X, y) < 1e-6


def test_gradient_check_without_regularisation():
    X, y = _data(seed=4)
    net = nn_numpy.NumpyMLP(5, hidden=(5, 4), l2=0.0, seed=5)
    _randomise_biases(net, seed=6)
    assert net.gradient_check(X, y) < 1e-6


def test_gradient_check_refuses_dropout():
    X, y = _data()
    net = nn_numpy.NumpyMLP(5, hidden=(4,), dropout=0.2)
    with pytest.raises(AssertionError):
        net.gradient_check(X, y)


def test_he_initialisation_scale():
    net = nn_numpy.NumpyMLP(400, hidden=(300,), seed=0)
    assert net.W[0].std() == pytest.approx(np.sqrt(2 / 400), rel=0.05)
    assert np.all(net.b[0] == 0)


def test_no_hidden_layer_is_linear_regression_and_learns_a_line():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(500, 3))
    y = 2.0 * X[:, 0] - 1.0 * X[:, 1] + 0.5
    net = nn_numpy.NumpyMLP(3, hidden=(), seed=0)
    net.fit(X, y, epochs=200, batch_size=64, lr=0.02)
    assert np.abs(net.predict(X) - y).mean() < 0.05
    assert len(net.W) == 1


def test_mlp_learns_a_nonlinear_function_better_than_linear():
    rng = np.random.default_rng(1)
    X = rng.uniform(-2, 2, size=(800, 1))
    y = np.abs(X[:, 0])                                    # V shape: a straight line cannot fit it
    lin = nn_numpy.NumpyMLP(1, hidden=(), seed=0).fit(X, y, epochs=150, lr=0.02)
    mlp = nn_numpy.NumpyMLP(1, hidden=(8,), seed=0).fit(X, y, epochs=150, lr=0.02)
    assert np.mean((mlp.predict(X) - y) ** 2) < 0.2 * np.mean((lin.predict(X) - y) ** 2)


def test_training_reduces_loss_and_early_stopping_restores_best_weights():
    X, y = _data(n=300, seed=2)
    y = X @ np.array([1.0, -1.0, 0.5, 0.0, 2.0])
    net = nn_numpy.NumpyMLP(5, hidden=(8,), seed=0)
    before = net.data_loss(net.forward(X)[0], y.reshape(-1, 1))
    net.fit(X[:200], y[:200], X[200:], y[200:], epochs=60, lr=0.01, patience=10)
    after = net.data_loss(net.forward(X)[0], y.reshape(-1, 1))
    assert after < before
    assert net.best_epoch >= 1


def test_dropout_is_only_active_in_training_mode():
    X, _ = _data()
    net = nn_numpy.NumpyMLP(5, hidden=(32,), dropout=0.5, seed=0)
    a, _ = net.forward(X, train=False)
    b, _ = net.forward(X, train=False)
    assert np.allclose(a, b)                               # deterministic at prediction time
    c, _ = net.forward(X, train=True)
    assert not np.allclose(a, c)                           # random mask during training


def test_same_seed_gives_same_network():
    X, y = _data(n=100)
    a = nn_numpy.NumpyMLP(5, hidden=(4,), seed=11).fit(X, y, epochs=5)
    b = nn_numpy.NumpyMLP(5, hidden=(4,), seed=11).fit(X, y, epochs=5)
    assert np.allclose(a.predict(X), b.predict(X))

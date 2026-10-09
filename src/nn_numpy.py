"""
nn_numpy.py - a small feed-forward neural network (MLP) written from scratch in NumPy.

Everything here is a standard building block from the Deep Learning Specialization:
  * layers      : Z = A_prev @ W + b ;   hidden activation = ReLU ;   output = linear (regression)
  * init        : He initialisation  W ~ N(0, 2 / n_in)
  * loss        : L = mean( 0.5 * (y_hat - y)^2 )  +  (lambda / 2) * sum(W^2)         (L2 regularisation)
  * backprop    : dZ_L = (y_hat - y)/m ;  dW = A_prev^T dZ + lambda*W ;  dA_prev = dZ W^T ;  dZ = dA * relu'(Z)
  * optimiser   : mini-batch gradient descent with Adam
  * optional    : inverted dropout on hidden layers
  * hidden=()   : NO hidden layer -> this is plain LINEAR REGRESSION (our first model, the sanity step)
  * gradient_check(): compares backprop with numerical gradients (see tests/test_nn_gradcheck.py)

No TensorFlow / PyTorch / Keras. ~150 lines you can explain on a whiteboard.
"""
import numpy as np


class NumpyMLP:
    def __init__(self, n_inputs, hidden=(16, 8), l2=0.0, dropout=0.0, seed=0):
        self.sizes = [n_inputs, *hidden, 1]
        self.l2 = l2
        self.dropout = dropout
        self.rng = np.random.default_rng(seed)
        self.W, self.b = [], []
        for n_in, n_out in zip(self.sizes[:-1], self.sizes[1:]):
            self.W.append(self.rng.normal(0.0, np.sqrt(2.0 / n_in), size=(n_in, n_out)))   # He init
            self.b.append(np.zeros((1, n_out)))
        self.history = {"train_loss": [], "dev_loss": []}

    # ------------------------------------------------------------------ forward / backward
    def forward(self, X, train=False):
        """Return predictions (m,1) and a cache for backprop."""
        A = X
        cache = {"A": [A], "Z": [], "mask": []}
        n_layers = len(self.W)
        for l in range(n_layers):
            Z = A @ self.W[l] + self.b[l]
            cache["Z"].append(Z)
            if l < n_layers - 1:                                   # hidden layer: ReLU (+ dropout)
                A = np.maximum(0.0, Z)
                if train and self.dropout > 0:
                    keep = 1.0 - self.dropout
                    mask = (self.rng.random(A.shape) < keep) / keep   # inverted dropout
                    A = A * mask
                    cache["mask"].append(mask)
                else:
                    cache["mask"].append(None)
            else:                                                  # output layer: linear
                A = Z
            cache["A"].append(A)
        return A, cache

    def data_loss(self, y_hat, y):
        return float(np.mean(0.5 * (y_hat - y) ** 2))

    def total_loss(self, X, y):
        """Data loss + L2 penalty, no dropout (used for gradient checking)."""
        y_hat, _ = self.forward(X, train=False)
        return self.data_loss(y_hat, y) + 0.5 * self.l2 * sum(float(np.sum(W ** 2)) for W in self.W)

    def backward(self, cache, y):
        m = y.shape[0]
        grads_W, grads_b = [None] * len(self.W), [None] * len(self.W)
        dZ = (cache["A"][-1] - y) / m                              # d(loss)/d(output)
        for l in reversed(range(len(self.W))):
            grads_W[l] = cache["A"][l].T @ dZ + self.l2 * self.W[l]
            grads_b[l] = dZ.sum(axis=0, keepdims=True)
            if l > 0:
                dA = dZ @ self.W[l].T
                if cache["mask"][l - 1] is not None:
                    dA = dA * cache["mask"][l - 1]
                dZ = dA * (cache["Z"][l - 1] > 0)                  # ReLU derivative
        return grads_W, grads_b

    # ------------------------------------------------------------------ training
    def fit(self, X, y, X_dev=None, y_dev=None, epochs=300, batch_size=64, lr=0.003,
            beta1=0.9, beta2=0.999, patience=30):
        """Mini-batch Adam. If a dev set is given: keep the weights with the lowest dev loss (early stopping)."""
        y = y.reshape(-1, 1)
        m = X.shape[0]
        mW = [np.zeros_like(w) for w in self.W]; vW = [np.zeros_like(w) for w in self.W]
        mb = [np.zeros_like(b) for b in self.b]; vb = [np.zeros_like(b) for b in self.b]
        t, best, best_weights, bad = 0, np.inf, None, 0
        for epoch in range(epochs):
            order = self.rng.permutation(m)
            for start in range(0, m, batch_size):
                idx = order[start:start + batch_size]
                y_hat, cache = self.forward(X[idx], train=True)
                gW, gb = self.backward(cache, y[idx])
                t += 1
                for l in range(len(self.W)):                      # Adam update
                    mW[l] = beta1 * mW[l] + (1 - beta1) * gW[l]; vW[l] = beta2 * vW[l] + (1 - beta2) * gW[l] ** 2
                    mb[l] = beta1 * mb[l] + (1 - beta1) * gb[l]; vb[l] = beta2 * vb[l] + (1 - beta2) * gb[l] ** 2
                    c1, c2 = 1 - beta1 ** t, 1 - beta2 ** t
                    self.W[l] -= lr * (mW[l] / c1) / (np.sqrt(vW[l] / c2) + 1e-8)
                    self.b[l] -= lr * (mb[l] / c1) / (np.sqrt(vb[l] / c2) + 1e-8)
            self.history["train_loss"].append(self.data_loss(self.forward(X)[0], y))
            if X_dev is not None:
                dev = self.data_loss(self.forward(X_dev)[0], y_dev.reshape(-1, 1))
                self.history["dev_loss"].append(dev)
                if dev < best - 1e-7:
                    best, bad = dev, 0
                    best_weights = ([w.copy() for w in self.W], [b.copy() for b in self.b])
                else:
                    bad += 1
                    if bad >= patience:
                        break
        if best_weights is not None:
            self.W, self.b = best_weights
        self.best_epoch = int(np.argmin(self.history["dev_loss"])) + 1 if X_dev is not None else len(self.history["train_loss"])
        return self

    def predict(self, X):
        return self.forward(X, train=False)[0].ravel()

    # ------------------------------------------------------------------ gradient checking
    def gradient_check(self, X, y, eps=1e-6):
        """
        Compare backprop gradients with numerical gradients (L(w+eps) - L(w-eps)) / (2 eps).
        Returns the relative difference; below ~1e-6 means backprop is correct.
        Requires dropout == 0 (a random mask would make the loss non-deterministic).
        """
        assert self.dropout == 0, "turn dropout off for gradient checking"
        y = y.reshape(-1, 1)
        _, cache = self.forward(X, train=False)
        gW, gb = self.backward(cache, y)
        analytic, numeric = [], []
        for params, grads in ((self.W, gW), (self.b, gb)):
            for p, g in zip(params, grads):
                it = np.nditer(p, flags=["multi_index"], op_flags=["readwrite"])
                while not it.finished:
                    i = it.multi_index
                    old = p[i]
                    p[i] = old + eps; plus = self.total_loss(X, y)
                    p[i] = old - eps; minus = self.total_loss(X, y)
                    p[i] = old
                    numeric.append((plus - minus) / (2 * eps))
                    analytic.append(g[i])
                    it.iternext()
        a, n = np.array(analytic), np.array(numeric)
        return float(np.linalg.norm(a - n) / (np.linalg.norm(a) + np.linalg.norm(n) + 1e-12))

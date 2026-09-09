"""Small tabular PyTorch classifier with the scikit-learn estimator contract."""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.utils.validation import check_is_fitted, validate_data


class TorchCreditClassifier(ClassifierMixin, BaseEstimator):
    """Predict Pago_atiempo; the network logit represents default (label zero).

    Learned weights are kept as CPU arrays, so joblib artifacts do not require
    CUDA to load or predict. PyTorch is imported only when this model is used.
    """

    def __init__(
        self,
        hidden_sizes=(64, 32),
        dropout=0.2,
        weight_decay=0.01,
        learning_rate=0.001,
        epochs=50,
        batch_size=512,
        class_weight=None,
        random_state=42,
        device="cpu",
    ):
        self.hidden_sizes = hidden_sizes
        self.dropout = dropout
        self.weight_decay = weight_decay
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        self.class_weight = class_weight
        self.random_state = random_state
        self.device = device

    def _network(self):
        import torch

        layers = []
        width = self.n_features_in_
        for size in self.hidden_sizes:
            layers.extend(
                [torch.nn.Linear(width, size), torch.nn.ReLU(),
                 torch.nn.Dropout(self.dropout)]
            )
            width = size
        layers.append(torch.nn.Linear(width, 1))
        return torch.nn.Sequential(*layers)

    def fit(self, X, y):
        import torch

        if (
            not self.hidden_sizes
            or any(not isinstance(n, int) or n < 1 for n in self.hidden_sizes)
            or not 0 <= self.dropout < 1
            or self.epochs < 1
            or self.batch_size < 1
            or self.learning_rate <= 0
            or self.weight_decay < 0
            or self.class_weight not in (None, "balanced")
            or self.device not in ("cpu", "cuda")
        ):
            raise ValueError("Invalid neural-network parameters")
        X, y = validate_data(self, X, y, dtype=np.float32)
        self.classes_ = np.unique(y)
        if not np.array_equal(self.classes_, [0, 1]):
            raise ValueError("Training requires both Pago_atiempo classes [0, 1]")
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA requested but PyTorch cannot access a GPU")
        # Preserve the caller's RNG and thread settings, including on failure.
        thread_count = torch.get_num_threads()
        try:
            torch.set_num_threads(1)
            devices = [torch.cuda.current_device()] if self.device == "cuda" else []
            with torch.random.fork_rng(devices=devices):
                torch.manual_seed(self.random_state)
                network = self._network().to(self.device)
                optimizer = torch.optim.AdamW(
                    network.parameters(), lr=self.learning_rate,
                    weight_decay=self.weight_decay,
                )
                inputs = torch.as_tensor(X, device=self.device)
                target = torch.as_tensor(
                    1 - y.astype(np.float32), device=self.device
                ).reshape(-1, 1)
                ratio = float((y == 1).sum() / (y == 0).sum())
                weight = ratio if self.class_weight == "balanced" else 1.0
                loss_fn = torch.nn.BCEWithLogitsLoss(
                    pos_weight=torch.tensor(weight, device=self.device)
                )
                generator = np.random.default_rng(self.random_state)
                self.loss_curve_ = []
                network.train()
                for _ in range(self.epochs):
                    order = generator.permutation(len(X))
                    total = 0.0
                    for start in range(0, len(X), self.batch_size):
                        indices = order[start:start + self.batch_size]
                        optimizer.zero_grad()
                        loss = loss_fn(network(inputs[indices]), target[indices])
                        if not torch.isfinite(loss):
                            raise ValueError("Non-finite neural-network training loss")
                        loss.backward()
                        optimizer.step()
                        total += float(loss.detach().cpu()) * len(indices)
                    self.loss_curve_.append(total / len(X))
                self.weights_ = {
                    key: value.detach().cpu().numpy().copy()
                    for key, value in network.state_dict().items()
                }
        finally:
            torch.set_num_threads(thread_count)
        self.training_device_ = self.device
        return self

    def predict_proba(self, X):
        import torch

        check_is_fitted(self, "weights_")
        X = validate_data(self, X, reset=False, dtype=np.float32)
        # Inference is deliberately CPU-only for portable deployment/benchmarks.
        thread_count = torch.get_num_threads()
        try:
            torch.set_num_threads(1)
            with torch.random.fork_rng(devices=[]):
                network = self._network()
                network.load_state_dict(
                    {key: torch.from_numpy(value)
                     for key, value in self.weights_.items()}
                )
                network.eval()
                with torch.no_grad():
                    chunks = [
                        torch.sigmoid(network(torch.as_tensor(batch))).numpy().ravel()
                        for batch in np.array_split(
                            X, max(1, int(np.ceil(len(X) / self.batch_size)))
                        )
                    ]
        finally:
            torch.set_num_threads(thread_count)
        default = np.concatenate(chunks)
        return np.column_stack([default, 1 - default])

    def predict(self, X):
        return np.where(self.predict_proba(X)[:, 0] >= 0.5, 0, 1)

"""Explainable credit-risk heuristic derived from the EDA findings.

The classifier consumes the shared output from ``ft_engineering.py``. It combines four
signals with equal default weights: high inquiry intensity, low DataCrédito score, low
bureau-to-declared income, and arrears on file. Percentile reference distributions and
probability calibration are fitted on training rows only.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.linear_model import LogisticRegression
from sklearn.utils.validation import check_is_fitted


COMPONENTS: tuple[tuple[str, str, str, float], ...] = (
    (
        "inquiry_intensity",
        "calc_intensidad_consulta",
        "missing__calc_intensidad_consulta",
        1.0,
    ),
    (
        "low_bureau_score",
        "puntaje_datacredito",
        "missing__puntaje_datacredito",
        -1.0,
    ),
    (
        "income_not_corroborated",
        "calc_desfase_ingresos",
        "missing__calc_desfase_ingresos",
        -1.0,
    ),
    (
        "arrears_on_file",
        "calc_tiene_mora",
        "missing__calc_tiene_mora",
        1.0,
    ),
)


class CreditRiskHeuristicClassifier(ClassifierMixin, BaseEstimator):
    """Rank applicants using the four leakage-free signals found in the EDA.

    Parameters
    ----------
    review_fraction:
        Share of the training population assigned to the high-risk/default class by
        ``predict``. The EDA used a 20% manual-review queue.
    component_weights:
        Weights for inquiry intensity, low bureau score, uncorroborated income, and
        arrears, respectively. The default preserves the EDA's equal-weight heuristic.
    calibration_C:
        Inverse regularization strength for the one-dimensional logistic probability
        calibration. Calibration never changes the risk ordering.

    Notes
    -----
    The source target is ``Pago_atiempo``: class 0 is default and class 1 is on time.
    ``predict_proba`` follows scikit-learn's class order and therefore returns default
    probability in column 0.
    """

    def __init__(
        self,
        review_fraction: float = 0.20,
        component_weights: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0),
        calibration_C: float = 1.0,
    ) -> None:
        self.review_fraction = review_fraction
        self.component_weights = component_weights
        self.calibration_C = calibration_C

    @staticmethod
    def _required_columns() -> list[str]:
        columns: list[str] = []
        for _, feature, missing_indicator, _ in COMPONENTS:
            columns.extend([feature, missing_indicator])
        return columns

    def _validate_parameters(self) -> np.ndarray:
        if not 0 < self.review_fraction < 1:
            raise ValueError("review_fraction must be strictly between 0 and 1")
        if self.calibration_C <= 0:
            raise ValueError("calibration_C must be greater than zero")
        weights = np.asarray(self.component_weights, dtype=float)
        if weights.shape != (len(COMPONENTS),):
            raise ValueError(f"component_weights must contain {len(COMPONENTS)} values")
        if not np.isfinite(weights).all() or (weights < 0).any() or weights.sum() == 0:
            raise ValueError(
                "component_weights must be finite, non-negative, and non-zero"
            )
        return weights

    def _select_inputs(self, X: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(X, pd.DataFrame):
            raise TypeError("CreditRiskHeuristicClassifier expects a pandas DataFrame")
        required = self._required_columns()
        missing = [column for column in required if column not in X.columns]
        if missing:
            raise ValueError(f"Missing heuristic input columns: {missing}")
        selected = X.loc[:, required].apply(pd.to_numeric, errors="coerce")
        for _, _, missing_indicator, _ in COMPONENTS:
            values = selected[missing_indicator]
            valid = values.isin([0, 1]) & values.notna()
            if not valid.all():
                raise ValueError(
                    f"{missing_indicator} must contain only binary 0/1 values"
                )
        return selected

    @staticmethod
    def _percentile(values: np.ndarray, reference: np.ndarray) -> np.ndarray:
        left = np.searchsorted(reference, values, side="left")
        right = np.searchsorted(reference, values, side="right")
        return (left + right + 1) / (2 * len(reference))

    def _component_frame(self, X: pd.DataFrame) -> pd.DataFrame:
        selected = self._select_inputs(X)
        components = pd.DataFrame(index=X.index)
        for name, feature, missing_indicator, direction in COMPONENTS:
            values = selected[feature].to_numpy(dtype=float)
            available = selected[missing_indicator].eq(0).to_numpy(copy=True)
            available &= np.isfinite(values)
            component = np.full(len(X), np.nan, dtype=float)
            if name in self.active_components_:
                if name == "arrears_on_file":
                    if ((values[available] < 0) | (values[available] > 1)).any():
                        raise ValueError("calc_tiene_mora must be between 0 and 1")
                    component[available] = values[available]
                else:
                    oriented = direction * values[available]
                    component[available] = self._percentile(
                        oriented, self.reference_values_[name]
                    )
            components[name] = component
        return components

    def _score_components(
        self, components: pd.DataFrame, *, fill_unscored: bool
    ) -> tuple[np.ndarray, np.ndarray]:
        values = components.to_numpy(dtype=float)
        available = np.isfinite(values)
        weighted = np.where(available, values * self.component_weights_, 0.0)
        denominators = np.where(available, self.component_weights_, 0.0).sum(axis=1)
        scores = np.divide(
            weighted.sum(axis=1),
            denominators,
            out=np.full(len(components), np.nan),
            where=denominators > 0,
        )
        counts = available.sum(axis=1)
        if fill_unscored:
            scores = np.where(np.isfinite(scores), scores, self.neutral_score_)
        return scores, counts

    def fit(
        self,
        X: pd.DataFrame,
        y: Any,
        sample_weight: Any = None,
    ) -> "CreditRiskHeuristicClassifier":
        """Fit percentile references, review threshold, and probability calibration."""
        self.component_weights_ = self._validate_parameters()
        selected = self._select_inputs(X)
        target = np.asarray(y)
        if target.ndim != 1 or len(target) != len(selected):
            raise ValueError("y must be one-dimensional and aligned with X")
        if not np.isin(target, [0, 1]).all():
            raise ValueError("y must contain only Pago_atiempo labels 0 and 1")
        if sample_weight is not None:
            sample_weight = np.asarray(sample_weight, dtype=float)
            if sample_weight.shape != (len(selected),):
                raise ValueError("sample_weight must have one value per row")

        self.feature_names_in_ = np.asarray(self._required_columns(), dtype=object)
        self.n_features_in_ = len(self.feature_names_in_)
        self.classes_ = np.asarray([0, 1], dtype=np.int8)
        self.reference_values_: dict[str, np.ndarray] = {}
        self.active_components_: list[str] = []
        for name, feature, missing_indicator, direction in COMPONENTS:
            values = selected[feature].to_numpy(dtype=float)
            available = selected[missing_indicator].eq(0).to_numpy(copy=True)
            available &= np.isfinite(values)
            if available.any():
                self.active_components_.append(name)
                if name != "arrears_on_file":
                    self.reference_values_[name] = np.sort(
                        direction * values[available]
                    )

        if not self.active_components_:
            raise ValueError(
                "At least one heuristic component must be available in training"
            )
        components = self._component_frame(X)
        training_scores, counts = self._score_components(
            components, fill_unscored=False
        )
        scored = np.isfinite(training_scores)
        if not scored.any():
            raise ValueError("No training row has an available heuristic component")
        self.neutral_score_ = float(np.median(training_scores[scored]))
        training_scores = np.where(
            np.isfinite(training_scores), training_scores, self.neutral_score_
        )
        self.review_threshold_ = float(
            np.quantile(training_scores, 1 - self.review_fraction, method="higher")
        )
        self.training_component_counts_ = counts
        self.training_risk_scores_ = training_scores

        default_target = (target == 0).astype(np.int8)
        self.training_default_rate_ = float(
            np.average(default_target, weights=sample_weight)
        )
        self.calibrator_: LogisticRegression | None = None
        if np.unique(default_target).size == 2:
            calibrator = LogisticRegression(C=self.calibration_C, solver="lbfgs")
            calibrator.fit(
                training_scores.reshape(-1, 1),
                default_target,
                sample_weight=sample_weight,
            )
            if float(calibrator.coef_[0, 0]) >= 0:
                self.calibrator_ = calibrator
        return self

    def risk_score(self, X: pd.DataFrame) -> np.ndarray:
        """Return the continuous 0–1 heuristic score; larger means riskier."""
        check_is_fitted(self, attributes=["reference_values_", "review_threshold_"])
        components = self._component_frame(X)
        scores, _ = self._score_components(components, fill_unscored=True)
        return scores

    def predict_review(self, X: pd.DataFrame) -> np.ndarray:
        """Return the operational high-risk/manual-review flag."""
        return self.risk_score(X) >= self.review_threshold_

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict 0 for the review/high-risk group and 1 otherwise."""
        return np.where(self.predict_review(X), 0, 1).astype(np.int8)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Return calibrated probabilities in class order ``[default, on-time]``."""
        check_is_fitted(self, attributes=["classes_", "training_default_rate_"])
        scores = self.risk_score(X)
        if self.calibrator_ is None:
            default_probability = np.full(len(scores), self.training_default_rate_)
        else:
            default_probability = self.calibrator_.predict_proba(
                scores.reshape(-1, 1)
            )[:, 1]
        return np.column_stack([default_probability, 1 - default_probability])

    def explain(self, X: pd.DataFrame) -> pd.DataFrame:
        """Return component risks, availability, final score, and review decision."""
        check_is_fitted(self, attributes=["reference_values_", "review_threshold_"])
        components = self._component_frame(X)
        scores, counts = self._score_components(components, fill_unscored=True)
        probabilities = self.predict_proba(X)[:, 0]
        explanation = components.add_prefix("component__")
        explanation["component_count"] = counts
        explanation["risk_score"] = scores
        explanation["default_probability"] = probabilities
        explanation["review_flag"] = scores >= self.review_threshold_
        return explanation

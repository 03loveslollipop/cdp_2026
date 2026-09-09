"""Tests for the EDA-derived credit-risk heuristic classifier."""

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.base import clone

from etl_scripts.src.ft_engineering import load_config, read_raw_data, split_and_prepare
from etl_scripts.src.heuristic_model import COMPONENTS, CreditRiskHeuristicClassifier


@pytest.fixture
def heuristic_data():
    return pd.DataFrame(
        {
            "calc_intensidad_consulta": [0, 1, 2, 3, 4, 5],
            "missing__calc_intensidad_consulta": [0, 0, 0, 0, 0, 0],
            "puntaje_datacredito": [900, 850, 800, 750, 700, 650],
            "missing__puntaje_datacredito": [0, 0, 0, 0, 0, 0],
            "calc_desfase_ingresos": [1.2, 1.1, 1.0, 0.9, 0.8, 0.7],
            "missing__calc_desfase_ingresos": [0, 0, 0, 0, 0, 0],
            "calc_tiene_mora": [0, 0, 0, 0, 1, 1],
            "missing__calc_tiene_mora": [0, 0, 0, 0, 0, 0],
        }
    )


@pytest.fixture
def heuristic_target():
    return pd.Series([1, 1, 1, 1, 0, 0], name="Pago_atiempo")


def test_risk_score_follows_eda_signal_directions(heuristic_data, heuristic_target):
    model = CreditRiskHeuristicClassifier().fit(heuristic_data, heuristic_target)
    scores = model.risk_score(heuristic_data)

    assert np.all(np.diff(scores) > 0)
    assert scores.min() >= 0
    assert scores.max() <= 1


def test_predict_uses_training_review_fraction(heuristic_data, heuristic_target):
    model = CreditRiskHeuristicClassifier(review_fraction=0.20).fit(
        heuristic_data, heuristic_target
    )

    review = model.predict_review(heuristic_data)
    predictions = model.predict(heuristic_data)
    assert review.sum() == 2
    assert np.array_equal(predictions == 0, review)
    assert model.classes_.tolist() == [0, 1]


def test_predict_proba_uses_default_as_column_zero(heuristic_data, heuristic_target):
    model = CreditRiskHeuristicClassifier().fit(heuristic_data, heuristic_target)
    probabilities = model.predict_proba(heuristic_data)

    assert probabilities.shape == (len(heuristic_data), 2)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1)
    assert probabilities[-1, 0] > probabilities[0, 0]


def test_missing_components_are_excluded_from_row_average(
    heuristic_data, heuristic_target
):
    model = CreditRiskHeuristicClassifier().fit(heuristic_data, heuristic_target)
    row = heuristic_data.iloc[[3]].copy()
    row.loc[:, "missing__puntaje_datacredito"] = 1
    row.loc[:, "missing__calc_desfase_ingresos"] = 1
    row.loc[:, "missing__calc_tiene_mora"] = 1

    explanation = model.explain(row)
    assert explanation.iloc[0]["component_count"] == 1
    assert explanation.iloc[0]["risk_score"] == pytest.approx(
        explanation.iloc[0]["component__inquiry_intensity"]
    )


def test_all_missing_components_receive_training_neutral_score(
    heuristic_data, heuristic_target
):
    model = CreditRiskHeuristicClassifier().fit(heuristic_data, heuristic_target)
    row = heuristic_data.iloc[[0]].copy()
    for column in row.filter(like="missing__"):
        row.loc[:, column] = 1

    explanation = model.explain(row)
    assert explanation.iloc[0]["component_count"] == 0
    assert explanation.iloc[0]["risk_score"] == pytest.approx(model.neutral_score_)


def test_unrelated_and_leaking_columns_cannot_change_predictions(
    heuristic_data, heuristic_target
):
    model = CreditRiskHeuristicClassifier().fit(heuristic_data, heuristic_target)
    baseline = model.risk_score(heuristic_data)
    augmented = heuristic_data.assign(
        puntaje=[-100, 100, -100, 100, -100, 100],
        Pago_atiempo=[0, 0, 0, 0, 0, 0],
    )

    np.testing.assert_allclose(model.risk_score(augmented), baseline)


def test_invalid_input_contract_is_rejected(heuristic_data, heuristic_target):
    model = CreditRiskHeuristicClassifier().fit(heuristic_data, heuristic_target)
    with pytest.raises(ValueError, match="Missing heuristic input columns"):
        model.predict(heuristic_data.drop(columns="calc_tiene_mora"))

    invalid_flag = heuristic_data.copy()
    invalid_flag.loc[0, "missing__calc_tiene_mora"] = 2
    with pytest.raises(ValueError, match="binary 0/1"):
        model.predict(invalid_flag)


def test_estimator_can_be_cloned_and_serialized(
    heuristic_data, heuristic_target, tmp_path
):
    model = clone(CreditRiskHeuristicClassifier(review_fraction=0.25))
    model.fit(heuristic_data, heuristic_target)
    path = tmp_path / "heuristic.joblib"
    joblib.dump(model, path)
    restored = joblib.load(path)

    np.testing.assert_allclose(
        restored.predict_proba(heuristic_data), model.predict_proba(heuristic_data)
    )


def test_invalid_parameters_and_target_are_rejected(heuristic_data, heuristic_target):
    with pytest.raises(ValueError, match="review_fraction"):
        CreditRiskHeuristicClassifier(review_fraction=1).fit(
            heuristic_data, heuristic_target
        )
    with pytest.raises(ValueError, match="component_weights"):
        CreditRiskHeuristicClassifier(component_weights=(1, 1, 1, -1)).fit(
            heuristic_data, heuristic_target
        )
    with pytest.raises(ValueError, match="Pago_atiempo"):
        CreditRiskHeuristicClassifier().fit(
            heuristic_data, pd.Series([1, 1, 2, 1, 0, 0])
        )


def test_model_integrates_with_full_chronological_pipeline():
    config = load_config()
    split, _ = split_and_prepare(read_raw_data(config), config)
    model = CreditRiskHeuristicClassifier().fit(
        split.train.predictors, split.train.target
    )

    probabilities = model.predict_proba(split.test.predictors)
    explanation = model.explain(split.test.predictors.iloc[:3])

    assert probabilities.shape == (3_229, 2)
    assert np.isfinite(probabilities).all()
    assert model.active_components_ == [component[0] for component in COMPONENTS]
    assert explanation["component_count"].between(0, 4).all()

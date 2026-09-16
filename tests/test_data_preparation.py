"""Regression tests for the shared predictive-data preparation contract."""

from pathlib import Path
import subprocess
import sys

import joblib
import numpy as np
import pandas as pd
import pytest

from mlops_pipeline.src.ft_engineering import (
    build_data_preparation_pipeline,
    chronological_train_test_split,
    extract_dataset,
    fit_prepare_training,
    get_pipeline_diagnostics,
    load_config,
    read_raw_data,
    split_and_prepare,
    transform_for_prediction,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.json"


@pytest.fixture
def config():
    return load_config(CONFIG_PATH)


@pytest.fixture
def raw_sample():
    return pd.DataFrame(
        {
            "tipo_credito": ["1", "68", "2"],
            "fecha_prestamo": [
                "15/01/2025 10:30",
                "20/02/2025 08:00",
                "21/03/2025 09:00",
            ],
            "capital_prestado": ["10000000", "0", "20000000"],
            "plazo_meses": ["12", "90", "24"],
            "edad_cliente": ["30", "122", "40"],
            "tipo_laboral": ["Empleado", "Independiente", "Empleado"],
            "salario_cliente": ["2000000", "22000000000", "4000000"],
            "total_otros_prestamos": ["200000", "100000", "400000"],
            "cuota_pactada": ["400000", "200000", "800000"],
            "puntaje": ["95,227787", "-1,5", "95,227787"],
            "puntaje_datacredito": ["800", "0", "700"],
            "cant_creditosvigentes": ["1", "0", "2"],
            "huella_consulta": ["4", "2", "3"],
            "saldo_mora": ["1", "", "0"],
            "saldo_total": ["8", "0", "16"],
            "saldo_principal": ["7", "0", "14"],
            "saldo_mora_codeudor": ["0", "0", "0"],
            "creditos_sectorFinanciero": ["1", "0", "1"],
            "creditos_sectorCooperativo": ["0", "0", "0"],
            "creditos_sectorReal": ["0", "", "1"],
            "promedio_ingresos_datacredito": ["1500000", "", "2000000"],
            "tendencia_ingresos": ["Creciente", "125000", "Estable"],
            "Pago_atiempo": ["1", "0", "1"],
            "post_outcome_note": ["x", "y", "z"],
        }
    )


def test_extract_dataset_separates_target_metadata_and_ignored_columns(
    raw_sample, config
):
    original = raw_sample.copy(deep=True)
    dataset = extract_dataset(raw_sample, config, require_target=True)

    pd.testing.assert_frame_equal(raw_sample, original)
    assert dataset.target.tolist() == [1, 0, 1]
    assert dataset.metadata.columns.tolist() == ["fecha_prestamo"]
    assert dataset.predictors.columns.tolist() == config["predictive_pipeline"][
        "required_predictors"
    ]
    assert dataset.ignored_columns == ("post_outcome_note",)
    assert set(dataset.excluded_columns_present) == {
        "Pago_atiempo",
        "puntaje",
        "saldo_mora_codeudor",
    }


def test_target_must_be_binary_and_is_never_imputed(raw_sample, config):
    invalid = raw_sample.copy()
    invalid.loc[1, "Pago_atiempo"] = ""
    with pytest.raises(ValueError, match="only 0 or 1"):
        extract_dataset(invalid, config, require_target=True)

    with pytest.raises(ValueError, match="must include target"):
        extract_dataset(
            raw_sample.drop(columns="Pago_atiempo"), config, require_target=True
        )


def test_chronological_split_is_deterministic_and_uses_70_30(raw_sample, config):
    shuffled = raw_sample.sample(frac=1, random_state=7)
    first = chronological_train_test_split(raw_sample, config)
    second = chronological_train_test_split(shuffled, config)

    assert first.train.index.tolist() == second.train.index.tolist() == [0, 1]
    assert first.test.index.tolist() == second.test.index.tolist() == [2]
    assert first.summary["requested_train_fraction"] == pytest.approx(0.70)
    assert first.summary["train_rows"] == 2
    assert first.summary["test_rows"] == 1
    train_dates = pd.to_datetime(first.train["fecha_prestamo"], dayfirst=True)
    test_dates = pd.to_datetime(first.test["fecha_prestamo"], dayfirst=True)
    assert train_dates.max() < test_dates.min()


def test_chronological_split_keeps_boundary_timestamp_together(raw_sample, config):
    repeated = pd.concat([raw_sample, raw_sample], ignore_index=True)
    repeated["fecha_prestamo"] = [
        "01/01/2025",
        "02/01/2025",
        "03/01/2025",
        "03/01/2025",
        "04/01/2025",
        "05/01/2025",
    ]
    split = chronological_train_test_split(repeated, config, train_fraction=0.5)

    train_dates = pd.to_datetime(split.train["fecha_prestamo"], dayfirst=True)
    test_dates = pd.to_datetime(split.test["fecha_prestamo"], dayfirst=True)
    assert set(train_dates).isdisjoint(set(test_dates))
    assert split.summary["boundary_adjustment_rows"] == 1
    assert len(split.train) == 2
    assert len(split.test) == 4


def test_chronological_split_rejects_invalid_dates(raw_sample, config):
    invalid = raw_sample.copy()
    invalid.loc[1, "fecha_prestamo"] = "not-a-date"
    with pytest.raises(ValueError, match="prevent chronological splitting"):
        chronological_train_test_split(invalid, config)


def test_pipeline_excludes_leakage_target_metadata_and_unknown_columns(
    raw_sample, config
):
    pipeline = build_data_preparation_pipeline(config)
    first = pipeline.fit_transform(raw_sample)
    changed = raw_sample.copy()
    changed["puntaje"] = ["-999", "999", "0"]
    changed["Pago_atiempo"] = ["0", "1", "0"]
    changed["post_outcome_note"] = ["changed"] * 3
    second = pipeline.transform(changed)

    pd.testing.assert_frame_equal(first, second)
    forbidden = {
        "puntaje",
        "Pago_atiempo",
        "fecha_prestamo",
        "saldo_mora_codeudor",
        "saldo_principal",
        "post_outcome_note",
    }
    assert forbidden.isdisjoint(first.columns)


def test_hard_invalid_values_are_imputed_while_plausible_extremes_survive(
    raw_sample, config
):
    prepared, pipeline = fit_prepare_training(raw_sample, config)
    result = prepared.predictors

    assert result.loc[1, "edad_cliente"] == pytest.approx(35)
    assert result.loc[1, "puntaje_datacredito"] == pytest.approx(750)
    assert result.loc[1, "capital_prestado"] == pytest.approx(15_000_000)
    assert result.loc[1, "salario_cliente"] == 22_000_000_000
    assert result.loc[1, "plazo_meses"] == 90
    assert result.loc[1, "missing__edad_cliente"] == 1
    assert result.loc[1, "missing__puntaje_datacredito"] == 1
    diagnostics = get_pipeline_diagnostics(pipeline)
    assert diagnostics["validation"]["hard_invalid__edad_cliente"] == 1
    assert diagnostics["validation"]["soft_warning__salario_cliente"] == 1
    assert diagnostics["validation"]["soft_warning__plazo_meses"] == 1


def test_units_and_eda_features_are_calculated_before_imputation(raw_sample, config):
    prepared, _ = fit_prepare_training(raw_sample, config)
    result = prepared.predictors

    assert result.loc[0, "saldo_total"] == 8_000
    assert result.loc[0, "saldo_mora"] == 1_000
    assert result.loc[0, "calc_ratio_cuota_salario"] == pytest.approx(0.2)
    assert result.loc[0, "calc_carga_financiera_total"] == pytest.approx(0.3)
    assert result.loc[0, "calc_intensidad_consulta"] == pytest.approx(2)
    assert result.loc[0, "calc_interes_devengado"] == pytest.approx(1_000)
    assert result.loc[0, "calc_tiene_mora"] == 1
    assert result.loc[1, "missing__calc_tiene_mora"] == 1
    assert result.loc[1, "missing__calc_sectores_distintos"] == 1
    assert result.loc[1, "missing__calc_creditos_no_reportados"] == 1
    assert result.loc[1, "missing__calc_ingreso_declarado_mayor"] == 1


def test_imputation_is_fitted_only_on_training_rows(raw_sample, config):
    training = raw_sample.iloc[[0, 2]].copy()
    _, pipeline = fit_prepare_training(training, config)
    prediction = raw_sample.iloc[[1]].drop(columns="Pago_atiempo")
    result = transform_for_prediction(prediction, pipeline, config).predictors

    assert result.iloc[0]["capital_prestado"] == pytest.approx(15_000_000)
    assert result.iloc[0]["edad_cliente"] == pytest.approx(35)
    assert result.iloc[0]["puntaje_datacredito"] == pytest.approx(750)
    assert result.iloc[0]["tendencia_ingresos"] == "Missing"


def test_split_and_prepare_fits_imputation_on_train_only(raw_sample, config):
    split, pipeline = split_and_prepare(raw_sample, config)

    assert split.train.predictors.shape == (2, 84)
    assert split.test.predictors.shape == (1, 84)
    assert split.train.target is not None and split.train.target.tolist() == [1, 0]
    assert split.test.target is not None and split.test.target.tolist() == [1]
    assert pipeline.named_steps["impute"].fill_values_["capital_prestado"] == (
        10_000_000
    )


def test_every_feature_has_a_stable_missingness_indicator(raw_sample, config):
    prepared, pipeline = fit_prepare_training(raw_sample, config)
    result = prepared.predictors
    base_features = pipeline.named_steps["impute"].feature_names_in_.tolist()

    assert result.columns.tolist() == pipeline.get_feature_names_out().tolist()
    assert all(f"missing__{column}" in result for column in base_features)
    assert result.shape[1] == 2 * len(base_features)
    assert not result.isna().any().any()
    numeric = result.select_dtypes(include="number").to_numpy(dtype=float)
    assert np.isfinite(numeric).all()


def test_all_missing_numeric_feature_uses_fallback_and_indicator(raw_sample, config):
    training = raw_sample.copy()
    training["saldo_mora"] = ""
    prepared, pipeline = fit_prepare_training(training, config)

    assert (prepared.predictors["saldo_mora"] == 0).all()
    assert (prepared.predictors["missing__saldo_mora"] == 1).all()
    diagnostics = get_pipeline_diagnostics(pipeline)
    assert "saldo_mora" in diagnostics["all_missing_numeric_fallbacks"]


def test_transform_is_batch_invariant_and_serializable(raw_sample, config, tmp_path):
    training = raw_sample.iloc[[0, 2]].copy()
    _, pipeline = fit_prepare_training(training, config)
    artifact = tmp_path / "credit_preparation.joblib"
    joblib.dump(pipeline, artifact)
    restored = joblib.load(artifact)

    batch = transform_for_prediction(raw_sample, restored, config).predictors
    single = transform_for_prediction(raw_sample.iloc[[1]], restored, config).predictors
    pd.testing.assert_frame_equal(batch.loc[[1]], single)


def test_cli_artifact_loads_from_imported_module(raw_sample, tmp_path):
    source = tmp_path / "training.csv"
    output = tmp_path / "predictors.csv"
    target = tmp_path / "target.csv"
    artifact = tmp_path / "preparation.joblib"
    raw_sample.to_csv(source, sep=";", index=False)

    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "mlops_pipeline" / "src" / "ft_engineering.py"),
            "fit",
            "--input",
            str(source),
            "--output",
            str(output),
            "--target-output",
            str(target),
            "--artifact",
            str(artifact),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    restored = joblib.load(artifact)
    assert restored.get_feature_names_out().shape == (84,)


def test_split_fit_cli_writes_both_partitions(raw_sample, tmp_path):
    source = tmp_path / "source.csv"
    train_output = tmp_path / "train_predictors.csv"
    test_output = tmp_path / "test_predictors.csv"
    train_target = tmp_path / "train_target.csv"
    test_target = tmp_path / "test_target.csv"
    artifact = tmp_path / "preparation.joblib"
    diagnostics = tmp_path / "split.json"
    raw_sample.to_csv(source, sep=";", index=False)

    subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "mlops_pipeline" / "src" / "ft_engineering.py"),
            "split-fit",
            "--input",
            str(source),
            "--train-output",
            str(train_output),
            "--test-output",
            str(test_output),
            "--train-target-output",
            str(train_target),
            "--test-target-output",
            str(test_target),
            "--artifact",
            str(artifact),
            "--diagnostics-output",
            str(diagnostics),
        ],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert pd.read_csv(train_output).shape == (2, 84)
    assert pd.read_csv(test_output).shape == (1, 84)
    report = pd.read_json(diagnostics, typ="series")
    assert report["split"]["train_rows"] == 2
    assert report["split"]["test_rows"] == 1


def test_missing_required_predictor_fails_during_fit_and_transform(raw_sample, config):
    pipeline = build_data_preparation_pipeline(config)
    with pytest.raises(ValueError, match="saldo_total"):
        pipeline.fit(raw_sample.drop(columns="saldo_total"))
    pipeline.fit(raw_sample)
    with pytest.raises(ValueError, match="saldo_total"):
        pipeline.transform(raw_sample.drop(columns="saldo_total"))


def test_full_dataset_contract(config):
    raw = read_raw_data(config)
    prepared, pipeline = fit_prepare_training(raw, config)
    result = prepared.predictors

    assert result.shape == (10_763, 84)
    assert result.index.equals(raw.index)
    assert not result.isna().any().any()
    assert "puntaje" not in result.columns
    assert "calc_n_reglas_violadas" in result.columns
    assert "calc_antiguedad_dias" not in result.columns
    assert prepared.target is not None and len(prepared.target) == len(result)
    assert pipeline.get_feature_names_out().tolist() == result.columns.tolist()


def test_full_dataset_uses_expected_chronological_70_30_split(config):
    raw = read_raw_data(config)
    split, _ = split_and_prepare(raw, config)

    assert len(split.train.predictors) == 7_534
    assert len(split.test.predictors) == 3_229
    assert split.summary["boundary_adjustment_rows"] == 0
    assert split.summary["train_end"] == "2025-05-26T13:31:00"
    assert split.summary["test_start"] == "2025-05-26T13:32:00"

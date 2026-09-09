"""Tests for the credit data-preparation pipeline."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from etl_scripts.src.ft_engineering import (
    build_data_preparation_pipeline,
    load_config,
    prepare_data,
    read_raw_data,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "etl_scripts" / "src" / "config.json"


@pytest.fixture
def config():
    return load_config(CONFIG_PATH)


@pytest.fixture
def raw_sample():
    return pd.DataFrame(
        {
            "tipo_credito": ["1", "2"],
            "fecha_prestamo": ["15/01/2025 10:30", "20/02/2025 08:00"],
            "capital_prestado": ["10000000", "0"],
            "plazo_meses": ["12", "0"],
            "edad_cliente": ["30", "17"],
            "tipo_laboral": ["Empleado", "Independiente"],
            "salario_cliente": ["2000000", " "],
            "total_otros_prestamos": ["200000", "100000"],
            "cuota_pactada": ["400000", "200000"],
            "puntaje": ["95,227787", "-1,5"],
            "puntaje_datacredito": ["800", "0"],
            "cant_creditosvigentes": ["1", "0"],
            "huella_consulta": ["4", "2"],
            "saldo_mora": ["1", ""],
            "saldo_total": ["8", "0"],
            "saldo_principal": ["7", "0"],
            "saldo_mora_codeudor": ["0", "0"],
            "creditos_sectorFinanciero": ["1", "0"],
            "creditos_sectorCooperativo": ["0", "0"],
            "creditos_sectorReal": ["0", "0"],
            "promedio_ingresos_datacredito": ["1500000", ""],
            "tendencia_ingresos": ["Creciente", "125000"],
            "Pago_atiempo": ["1", "0"],
        }
    )


def test_pipeline_applies_cleaning_units_and_types(raw_sample, config):
    original = raw_sample.copy(deep=True)
    result = prepare_data(raw_sample, config)

    pd.testing.assert_frame_equal(raw_sample, original)
    assert result.loc[0, "saldo_total"] == 8_000
    assert result.loc[0, "saldo_mora"] == 1_000
    assert pd.isna(result.loc[1, "puntaje_datacredito"])
    assert pd.api.types.is_datetime64_any_dtype(result["fecha_prestamo"])
    assert isinstance(result["tipo_laboral"].dtype, pd.CategoricalDtype)


def test_pipeline_creates_eda_features(raw_sample, config):
    result = prepare_data(raw_sample, config)

    assert result.loc[0, "calc_ratio_cuota_salario"] == pytest.approx(0.2)
    assert result.loc[0, "calc_carga_financiera_total"] == pytest.approx(0.3)
    assert result.loc[0, "calc_intensidad_consulta"] == pytest.approx(2.0)
    assert result.loc[0, "calc_interes_devengado"] == pytest.approx(1_000)
    assert result.loc[0, "calc_tiene_mora"] == 1.0
    assert pd.isna(result.loc[1, "calc_tiene_mora"])
    assert result.loc[1, "calc_sin_score_bureau"] == 1.0
    assert result.loc[0, "calc_antiguedad_dias"] == 35
    assert result.loc[1, "calc_antiguedad_dias"] == 0


def test_pipeline_preserves_missing_values_and_excludes_leakage(raw_sample, config):
    result = build_data_preparation_pipeline(config).fit_transform(raw_sample)

    assert pd.isna(result.loc[1, "salario_cliente"])
    assert pd.isna(result.loc[1, "calc_ratio_cuota_salario"])
    assert "puntaje" not in result.columns
    assert "saldo_mora_codeudor" not in result.columns
    assert "delta_ingresos_datacredito" not in result.columns
    assert "calc_n_reglas_violadas" in result.columns
    assert "calc_n_reglas_violadas_todas" not in result.columns


def test_pipeline_requires_complete_feature_schema(raw_sample, config):
    with pytest.raises(ValueError, match="saldo_total"):
        prepare_data(raw_sample.drop(columns="saldo_total"), config)


def test_pipeline_accepts_inference_data_without_target(raw_sample, config):
    result = prepare_data(raw_sample.drop(columns="Pago_atiempo"), config)
    assert "Pago_atiempo" not in result.columns
    assert len(result) == len(raw_sample)


def test_full_dataset_smoke_test(config):
    raw = read_raw_data(config)
    result = prepare_data(raw, config)

    assert result.shape == (10_763, 49)
    assert result.index.equals(raw.index)
    assert not set(config["leakage_columns"]) & set(result.columns)
    numeric_values = result.select_dtypes(include="number").to_numpy(dtype=float)
    assert np.isfinite(numeric_values[~np.isnan(numeric_values)]).all()

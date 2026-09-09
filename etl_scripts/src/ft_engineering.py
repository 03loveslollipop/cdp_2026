"""Production-oriented preparation and feature-engineering pipeline from the EDA.

The pipeline standardises the raw extract, applies the unit correction documented in
``config.json``, creates the leakage-free calculated variables, and returns the modelling
frame defined in section 5.1 of the EDA. It deliberately does not impute missing values,
remove rows, or repair outliers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline


DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the pipeline configuration from JSON."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _required_feature_columns(config: dict[str, Any]) -> set[str]:
    schema = config["schema"]
    groups = (
        schema["categorical_nominal"],
        schema["categorical_ordinal"],
        schema["counts_discrete"],
        schema["monetary"],
        schema["scores"],
        config["read_csv"]["date_columns"],
    )
    return set().union(*groups)


class CreditDataCleaner(BaseEstimator, TransformerMixin):
    """Standardise nulls and types, isolate contamination, and correct units."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fit(self, X: pd.DataFrame, y: Any = None) -> "CreditDataCleaner":
        missing = _required_feature_columns(self.config) - set(X.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(X, pd.DataFrame):
            raise TypeError("CreditDataCleaner expects a pandas DataFrame")

        cfg = self.config
        schema = cfg["schema"]
        target = schema["target"]
        df = X.copy(deep=True)

        # Preserve the source's own missing-value representation until this step.
        null_tokens = set(cfg["null_tokens"])
        for column in df.select_dtypes(include=["object", "string"]).columns:
            values = df[column].astype("string").str.strip()
            df[column] = values.mask(values.isin(null_tokens))

        # A small block of numeric income deltas contaminated the ordinal trend field.
        trend_column = "tendencia_ingresos"
        valid_trends = cfg["valid_labels"][trend_column]
        trend = df[trend_column]
        valid_label = trend.isin(valid_trends)
        df["delta_ingresos_datacredito"] = pd.to_numeric(
            trend.where(trend.notna() & ~valid_label), errors="coerce"
        )
        df[trend_column] = trend.where(valid_label)

        for column in cfg["read_csv"]["decimal_comma_columns"]:
            df[column] = df[column].astype("string").str.replace(",", ".", regex=False)

        for column in cfg["read_csv"]["date_columns"]:
            df[column] = pd.to_datetime(
                df[column],
                dayfirst=cfg["read_csv"]["date_dayfirst"],
                format="mixed",
                errors="coerce",
            )

        numeric_columns = (
            schema["monetary"]
            + schema["counts_discrete"]
            + schema["scores"]
            + ["tipo_credito"]
        )
        if target in df.columns:
            numeric_columns.append(target)
        for column in dict.fromkeys(numeric_columns):
            df[column] = pd.to_numeric(df[column], errors="coerce")

        # The internal leaking score is removed later; its sentinel is immaterial here.
        for column, sentinels in cfg["sentinels"].items():
            if column in df.columns and column not in cfg["leakage_columns"]:
                df[column] = df[column].replace(sentinels, np.nan)

        for column in schema["counts_discrete"]:
            df[column] = df[column].astype("Int64")
        df["tipo_credito"] = df["tipo_credito"].astype("Int64").astype("category")
        df["tipo_laboral"] = pd.Categorical(
            df["tipo_laboral"], categories=cfg["valid_labels"]["tipo_laboral"]
        )
        df[trend_column] = pd.Categorical(
            df[trend_column], categories=valid_trends, ordered=True
        )
        if target in df.columns:
            df[target] = df[target].astype("Int8")

        scale = cfg["unit_scale"]
        for column in scale["columns"]:
            if column in df.columns:
                df[column] = df[column].astype(float) * scale["factor"]
        return df


class CreditFeatureEngineer(BaseEstimator, TransformerMixin):
    """Add the leakage-free calculated variables established during EDA."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fit(self, X: pd.DataFrame, y: Any = None) -> "CreditFeatureEngineer":
        dates = X["fecha_prestamo"]
        self.reference_date_ = dates.max()
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not hasattr(self, "reference_date_"):
            raise RuntimeError("CreditFeatureEngineer must be fitted before transform")

        cfg = self.config
        df = X.copy(deep=True)
        salary = df["salario_cliente"].replace(0, np.nan)
        capital = df["capital_prestado"].replace(0, np.nan)
        accounts = df["cant_creditosvigentes"].astype(float).replace(0, np.nan)
        calc = pd.DataFrame(index=df.index)

        calc["ratio_cuota_salario"] = df["cuota_pactada"] / salary
        calc["ratio_pagos_otros_salario"] = df["total_otros_prestamos"] / salary
        calc["ratio_capital_salario"] = df["capital_prestado"] / salary
        calc["carga_financiera_total"] = (
            df["cuota_pactada"] + df["total_otros_prestamos"]
        ) / salary

        calc["cuota_sobre_capital"] = df["cuota_pactada"] / capital
        calc["cobertura_cuotas"] = df["cuota_pactada"] * df["plazo_meses"] / capital
        positive_capital = df["capital_prestado"].astype(float)
        positive_capital = positive_capital.mask(positive_capital <= 0)
        calc["log_capital"] = np.log10(positive_capital)

        calc["intensidad_consulta"] = df["huella_consulta"] / (
            df["cant_creditosvigentes"].astype(float) + 1
        )
        adult_years = (df["edad_cliente"].astype(float) - 18).clip(lower=1)
        calc["creditos_por_anio_adulto"] = (
            df["cant_creditosvigentes"].astype(float) / adult_years
        )
        sectors = [
            "creditos_sectorFinanciero",
            "creditos_sectorCooperativo",
            "creditos_sectorReal",
        ]
        calc["share_sector_financiero"] = df[sectors[0]] / accounts
        calc["share_sector_real"] = df[sectors[2]] / accounts
        calc["share_sector_cooperativo"] = df[sectors[1]] / accounts
        calc["sectores_distintos"] = (df[sectors].astype(float) > 0).sum(axis=1)
        calc["creditos_no_reportados"] = (
            df["cant_creditosvigentes"].astype(float) - df[sectors].astype(float).sum(axis=1)
        )

        calc["tiene_mora"] = (df["saldo_mora"] > 0).astype(float).where(
            df["saldo_mora"].notna()
        )
        calc["ratio_mora_saldo"] = df["saldo_mora"] / df["saldo_total"].replace(0, np.nan)
        calc["interes_devengado"] = df["saldo_total"] - df["saldo_principal"]
        calc["saldo_por_credito"] = df["saldo_total"] / accounts
        calc["ratio_saldo_capital"] = df["saldo_total"] / capital

        bureau_income = df["promedio_ingresos_datacredito"]
        calc["desfase_ingresos"] = bureau_income / salary
        calc["ingreso_declarado_mayor"] = (salary > bureau_income).astype(float)
        calc["sin_info_ingresos_bureau"] = bureau_income.isna().astype(float)
        calc["sin_score_bureau"] = df["puntaje_datacredito"].isna().astype(float)

        violations = pd.DataFrame(index=df.index)
        safe_rules = {
            column: bounds
            for column, bounds in cfg["validation_rules"].items()
            if column not in cfg["leakage_columns"]
        }
        for column, bounds in safe_rules.items():
            values = pd.to_numeric(df[column], errors="coerce")
            violations[column] = (values < bounds["min"]) | (values > bounds["max"])
        calc["n_reglas_violadas"] = violations.sum(axis=1)

        dates = df["fecha_prestamo"]
        calc["mes_desembolso"] = dates.dt.month
        calc["dia_semana_desembolso"] = dates.dt.dayofweek
        calc["hora_desembolso"] = dates.dt.hour
        calc["antiguedad_dias"] = (self.reference_date_ - dates).dt.days
        calc = calc.replace([np.inf, -np.inf], np.nan).add_prefix("calc_")

        # Match the notebook's modelling frame and prevent direct or indirect leakage.
        helper_columns = ["delta_ingresos_datacredito", "n_reglas_violadas_todas"]
        drop_columns = list(
            dict.fromkeys(cfg["drop_columns"] + cfg["leakage_columns"] + helper_columns)
        )
        prepared = pd.concat([df.drop(columns=drop_columns, errors="ignore"), calc], axis=1)
        leaked = set(cfg["leakage_columns"]) & set(prepared.columns)
        if leaked:
            raise AssertionError(f"Leakage columns reached prepared data: {sorted(leaked)}")
        return prepared


def build_data_preparation_pipeline(
    config: dict[str, Any] | None = None,
) -> Pipeline:
    """Build an unfitted scikit-learn pipeline for raw credit records."""
    cfg = config or load_config()
    return Pipeline(
        steps=[
            ("clean", CreditDataCleaner(cfg)),
            ("derive_features", CreditFeatureEngineer(cfg)),
        ]
    )


def prepare_data(
    data: pd.DataFrame, config: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Convenience function that fits and transforms a raw DataFrame."""
    return build_data_preparation_pipeline(config).fit_transform(data)


def read_raw_data(
    config: dict[str, Any] | None = None,
    input_path: str | Path | None = None,
    config_dir: str | Path = DEFAULT_CONFIG_PATH.parent,
) -> pd.DataFrame:
    """Read the raw extract using the configured delimiter and encoding."""
    cfg = config or load_config()
    path = (
        Path(input_path)
        if input_path
        else (Path(config_dir) / cfg["paths"]["raw_data"]).resolve()
    )
    return pd.read_csv(
        path,
        sep=cfg["read_csv"]["sep"],
        encoding=cfg["read_csv"]["encoding"],
        dtype=str,
        keep_default_na=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the credit-payment dataset")
    parser.add_argument("--input", type=Path, help="Raw CSV; defaults to config.json")
    parser.add_argument("--output", type=Path, required=True, help="Destination CSV")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()

    cfg = load_config(args.config)
    raw = read_raw_data(cfg, args.input, args.config.parent)
    prepared = prepare_data(raw, cfg)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(args.output, index=False)
    print(
        f"Prepared {len(prepared):,} rows and "
        f"{prepared.shape[1]} columns -> {args.output}"
    )


if __name__ == "__main__":
    main()

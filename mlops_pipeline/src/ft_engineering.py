"""Leakage-safe shared preparation for credit-payment predictive models.

The shared pipeline ends after fitted imputation. Encoding, scaling, feature selection,
and estimation belong to each model-specific pipeline. Split data before calling ``fit``:
all learned fill values must come from the training partition only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline


DEFAULT_CONFIG_PATH = Path(__file__).parents[2] / "config.json"
INTERNAL_RULE_COUNT = "__n_reglas_violadas"

DERIVED_FEATURE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "calc_ratio_cuota_salario": ("cuota_pactada", "salario_cliente"),
    "calc_ratio_pagos_otros_salario": ("total_otros_prestamos", "salario_cliente"),
    "calc_ratio_capital_salario": ("capital_prestado", "salario_cliente"),
    "calc_carga_financiera_total": (
        "cuota_pactada",
        "total_otros_prestamos",
        "salario_cliente",
    ),
    "calc_cuota_sobre_capital": ("cuota_pactada", "capital_prestado"),
    "calc_cobertura_cuotas": ("cuota_pactada", "plazo_meses", "capital_prestado"),
    "calc_log_capital": ("capital_prestado",),
    "calc_intensidad_consulta": ("huella_consulta", "cant_creditosvigentes"),
    "calc_creditos_por_anio_adulto": ("cant_creditosvigentes", "edad_cliente"),
    "calc_share_sector_financiero": (
        "creditos_sectorFinanciero",
        "cant_creditosvigentes",
    ),
    "calc_share_sector_real": ("creditos_sectorReal", "cant_creditosvigentes"),
    "calc_share_sector_cooperativo": (
        "creditos_sectorCooperativo",
        "cant_creditosvigentes",
    ),
    "calc_sectores_distintos": (
        "creditos_sectorFinanciero",
        "creditos_sectorCooperativo",
        "creditos_sectorReal",
    ),
    "calc_creditos_no_reportados": (
        "cant_creditosvigentes",
        "creditos_sectorFinanciero",
        "creditos_sectorCooperativo",
        "creditos_sectorReal",
    ),
    "calc_tiene_mora": ("saldo_mora",),
    "calc_ratio_mora_saldo": ("saldo_mora", "saldo_total"),
    "calc_interes_devengado": ("saldo_total", "saldo_principal"),
    "calc_saldo_por_credito": ("saldo_total", "cant_creditosvigentes"),
    "calc_ratio_saldo_capital": ("saldo_total", "capital_prestado"),
    "calc_desfase_ingresos": (
        "promedio_ingresos_datacredito",
        "salario_cliente",
    ),
    "calc_ingreso_declarado_mayor": (
        "salario_cliente",
        "promedio_ingresos_datacredito",
    ),
    "calc_sin_info_ingresos_bureau": ("promedio_ingresos_datacredito",),
    "calc_sin_score_bureau": ("puntaje_datacredito",),
    "calc_n_reglas_violadas": (INTERNAL_RULE_COUNT,),
}


@dataclass(frozen=True)
class CreditDataset:
    """Separated modelling inputs, optional label, and split metadata."""

    predictors: pd.DataFrame
    target: pd.Series | None
    metadata: pd.DataFrame
    ignored_columns: tuple[str, ...] = ()
    excluded_columns_present: tuple[str, ...] = ()


@dataclass(frozen=True)
class RawCreditSplit:
    """Raw chronological partitions and their reproducibility metadata."""

    train: pd.DataFrame
    test: pd.DataFrame
    summary: dict[str, Any]


@dataclass(frozen=True)
class PreparedCreditSplit:
    """Prepared train/test datasets and diagnostics from their shared pipeline."""

    train: CreditDataset
    test: CreditDataset
    summary: dict[str, Any]
    train_diagnostics: dict[str, Any]
    test_diagnostics: dict[str, Any]


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the project configuration."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _require_frame(X: Any) -> pd.DataFrame:
    if not isinstance(X, pd.DataFrame):
        raise TypeError("The credit preparation pipeline expects a pandas DataFrame")
    return X


def _null_tokens(config: dict[str, Any]) -> set[str]:
    return {str(value).strip() for value in config["null_tokens"]}


def _numeric_input_columns(config: dict[str, Any]) -> list[str]:
    predictive = config["predictive_pipeline"]
    categorical = set(predictive["categorical_predictors"]) - {"tipo_credito"}
    return [
        column
        for column in predictive["required_predictors"]
        if column not in categorical
    ]


def chronological_train_test_split(
    raw: pd.DataFrame,
    config: dict[str, Any] | None = None,
    *,
    train_fraction: float | None = None,
) -> RawCreditSplit:
    """Split raw rows oldest-first, keeping equal timestamps in one partition."""
    frame = _require_frame(raw)
    cfg = config or load_config()
    split_config = cfg["predictive_pipeline"]["train_test_split"]
    fraction = (
        float(split_config["train_fraction"])
        if train_fraction is None
        else float(train_fraction)
    )
    if not 0 < fraction < 1:
        raise ValueError("train_fraction must be strictly between 0 and 1")
    if len(frame) < 2:
        raise ValueError("At least two rows are required for a train/test split")

    timestamp_column = split_config["timestamp_column"]
    if timestamp_column not in frame.columns:
        raise ValueError(
            f"Chronological split requires timestamp column {timestamp_column!r}"
        )
    raw_dates = frame[timestamp_column].astype("string").str.strip()
    raw_dates = raw_dates.mask(raw_dates.isin(_null_tokens(cfg)))
    dates = pd.to_datetime(
        raw_dates,
        dayfirst=cfg["read_csv"]["date_dayfirst"],
        format="mixed",
        errors="coerce",
    )
    invalid_dates = dates.isna()
    if invalid_dates.any():
        indices = frame.index[invalid_dates].tolist()[:10]
        raise ValueError(
            f"Invalid {timestamp_column} values prevent chronological splitting; "
            f"rows include {indices}"
        )

    order = np.argsort(dates.to_numpy(), kind="stable")
    ordered = frame.iloc[order].copy(deep=True)
    ordered_dates = dates.iloc[order].reset_index(drop=True)
    nominal_train_rows = int(len(ordered) * fraction)
    if nominal_train_rows < 1 or nominal_train_rows >= len(ordered):
        raise ValueError("train_fraction leaves an empty train or test partition")

    train_rows = nominal_train_rows
    if split_config["keep_timestamp_groups_together"]:
        first_test_date = ordered_dates.iloc[train_rows]
        while train_rows > 0 and ordered_dates.iloc[train_rows - 1] == first_test_date:
            train_rows -= 1
        if train_rows == 0:
            raise ValueError(
                "The timestamp grouping rule leaves an empty training partition"
            )

    train = ordered.iloc[:train_rows].copy(deep=True)
    test = ordered.iloc[train_rows:].copy(deep=True)
    train_dates = ordered_dates.iloc[:train_rows]
    test_dates = ordered_dates.iloc[train_rows:]
    summary = {
        "strategy": "chronological",
        "timestamp_column": timestamp_column,
        "requested_train_fraction": fraction,
        "actual_train_fraction": train_rows / len(ordered),
        "total_rows": len(ordered),
        "train_rows": len(train),
        "test_rows": len(test),
        "train_start": train_dates.iloc[0].isoformat(),
        "train_end": train_dates.iloc[-1].isoformat(),
        "test_start": test_dates.iloc[0].isoformat(),
        "test_end": test_dates.iloc[-1].isoformat(),
        "boundary_adjustment_rows": nominal_train_rows - train_rows,
    }
    return RawCreditSplit(train=train, test=test, summary=summary)


def extract_dataset(
    raw: pd.DataFrame,
    config: dict[str, Any] | None = None,
    *,
    require_target: bool = False,
) -> CreditDataset:
    """Separate raw predictors, target, and date metadata before any fitted work."""
    frame = _require_frame(raw)
    cfg = config or load_config()
    contract = cfg["predictive_pipeline"]
    required = contract["required_predictors"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required predictor columns: {missing}")

    target_name = cfg["schema"]["target"]
    target: pd.Series | None = None
    if target_name in frame.columns:
        raw_target = frame[target_name].astype("string").str.strip()
        raw_target = raw_target.mask(raw_target.isin(_null_tokens(cfg)))
        target = pd.to_numeric(raw_target, errors="coerce")
        invalid = target.isna() | ~target.isin([0, 1])
        if invalid.any():
            indices = frame.index[invalid].tolist()[:10]
            raise ValueError(
                f"{target_name} must contain only 0 or 1; invalid rows include {indices}"
            )
        target = target.astype("int8").rename(target_name)
    elif require_target:
        raise ValueError(f"Training data must include target column {target_name!r}")

    metadata = pd.DataFrame(index=frame.index)
    for column in contract["metadata_columns"]:
        if column in frame.columns:
            metadata[column] = pd.to_datetime(
                frame[column],
                dayfirst=cfg["read_csv"]["date_dayfirst"],
                format="mixed",
                errors="coerce",
            )

    known = set(required) | set(contract["metadata_columns"])
    known |= set(contract["known_excluded_columns"])
    ignored = tuple(column for column in frame.columns if column not in known)
    excluded = tuple(
        column
        for column in contract["known_excluded_columns"]
        if column in frame.columns
    )
    return CreditDataset(
        predictors=frame.loc[:, required].copy(deep=True),
        target=target,
        metadata=metadata,
        ignored_columns=ignored,
        excluded_columns_present=excluded,
    )


class PredictorSelector(TransformerMixin, BaseEstimator):
    """Enforce the raw predictor allowlist and discard every other column."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fit(self, X: pd.DataFrame, y: Any = None) -> "PredictorSelector":
        frame = _require_frame(X)
        required = self.config["predictive_pipeline"]["required_predictors"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"Missing required predictor columns: {missing}")
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.feature_names_out_ = np.asarray(required, dtype=object)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        frame = _require_frame(X)
        required = self.config["predictive_pipeline"]["required_predictors"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"Missing required predictor columns: {missing}")
        known_excluded = set(
            self.config["predictive_pipeline"]["known_excluded_columns"]
        )
        self.excluded_columns_present_ = tuple(
            column for column in frame.columns if column in known_excluded
        )
        self.ignored_columns_ = tuple(
            column
            for column in frame.columns
            if column not in required and column not in known_excluded
        )
        return frame.loc[:, required].copy(deep=True)

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return self.feature_names_out_.copy()


class CreditDataCleaner(TransformerMixin, BaseEstimator):
    """Standardize nulls, parse types, remove sentinels, and correct units."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fit(self, X: pd.DataFrame, y: Any = None) -> "CreditDataCleaner":
        frame = _require_frame(X)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        frame = _require_frame(X)
        cfg = self.config
        df = frame.copy(deep=True)
        nulls = _null_tokens(cfg)

        for column in df.columns:
            if pd.api.types.is_object_dtype(df[column]) or isinstance(
                df[column].dtype, pd.StringDtype
            ):
                values = df[column].astype("string").str.strip()
                df[column] = values.mask(values.isin(nulls))

        parse_failures: dict[str, pd.Series] = {}
        for column in _numeric_input_columns(cfg):
            before = df[column].notna()
            if column in cfg["read_csv"]["decimal_comma_columns"]:
                df[column] = (
                    df[column].astype("string").str.replace(",", ".", regex=False)
                )
            converted = pd.to_numeric(df[column], errors="coerce")
            parse_failures[column] = before & converted.isna()
            df[column] = converted.astype(float)

        trend_column = "tendencia_ingresos"
        valid_trends = cfg["valid_labels"][trend_column]
        trend = df[trend_column].astype("string")
        self.trend_contamination_ = trend.notna() & ~trend.isin(valid_trends)
        df[trend_column] = trend.where(trend.isin(valid_trends))

        for column, valid_labels in cfg["valid_labels"].items():
            if column == trend_column:
                continue
            values = df[column].astype("string")
            self.__dict__.setdefault("invalid_categories_", {})[column] = (
                values.notna() & ~values.isin(valid_labels)
            )
            df[column] = values.where(values.isin(valid_labels))

        sentinel_flags: dict[str, pd.Series] = {}
        for column, sentinels in cfg["sentinels"].items():
            if column in df.columns and column not in cfg["leakage_columns"]:
                sentinel_flags[column] = df[column].isin(sentinels)
                df[column] = df[column].replace(sentinels, np.nan)

        scale = cfg["unit_scale"]
        for column in scale["columns"]:
            if column in df.columns:
                df[column] = df[column].astype(float) * scale["factor"]

        self.row_diagnostics_ = pd.DataFrame(index=df.index)
        for column, flag in parse_failures.items():
            self.row_diagnostics_[f"parse_failure__{column}"] = flag.astype(bool)
        self.row_diagnostics_[f"invalid_category__{trend_column}"] = (
            self.trend_contamination_.astype(bool)
        )
        for column, flag in getattr(self, "invalid_categories_", {}).items():
            self.row_diagnostics_[f"invalid_category__{column}"] = flag.astype(bool)
        for column, flag in sentinel_flags.items():
            self.row_diagnostics_[f"sentinel__{column}"] = flag.astype(bool)
        self.validation_report_ = {
            column: int(values.sum())
            for column, values in self.row_diagnostics_.items()
            if values.any()
        }
        return df

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return self.feature_names_in_.copy()


class CreditDataValidator(TransformerMixin, BaseEstimator):
    """Null hard-invalid values and retain soft-range anomalies with flags."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fit(self, X: pd.DataFrame, y: Any = None) -> "CreditDataValidator":
        frame = _require_frame(X)
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.feature_names_out_ = np.append(self.feature_names_in_, INTERNAL_RULE_COUNT)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        df = _require_frame(X).copy(deep=True)
        contract = self.config["predictive_pipeline"]
        hard = contract["hard_validation"]
        hard_by_column = {
            column: pd.Series(False, index=df.index) for column in df.columns
        }

        for column, bounds in hard["ranges"].items():
            values = df[column]
            hard_by_column[column] |= values.notna() & (
                (values < bounds["min"]) | (values > bounds["max"])
            )
        for column in hard["positive"]:
            hard_by_column[column] |= df[column].notna() & (df[column] <= 0)
        for column in hard["non_negative"]:
            hard_by_column[column] |= df[column].notna() & (df[column] < 0)
        for column in hard["integer"]:
            values = df[column]
            hard_by_column[column] |= values.notna() & ~np.isclose(
                values, np.round(values)
            )

        soft_by_column: dict[str, pd.Series] = {}
        for column, bounds in contract["soft_validation_rules"].items():
            values = df[column]
            flag = pd.Series(False, index=df.index)
            if "min" in bounds:
                flag |= values.notna() & (values < bounds["min"])
            if "max" in bounds:
                flag |= values.notna() & (values > bounds["max"])
            soft_by_column[column] = flag

        violations = pd.DataFrame(index=df.index)
        for column in df.columns:
            hard_flag = hard_by_column[column]
            soft_flag = soft_by_column.get(
                column, pd.Series(False, index=df.index)
            )
            if hard_flag.any() or soft_flag.any():
                violations[column] = hard_flag | soft_flag
            if hard_flag.any():
                df.loc[hard_flag, column] = np.nan

        df["tipo_credito"] = df["tipo_credito"].map(
            lambda value: pd.NA if pd.isna(value) else str(int(value))
        ).astype("string")
        for column in ["tipo_laboral", "tendencia_ingresos"]:
            df[column] = df[column].astype("string")

        df[INTERNAL_RULE_COUNT] = violations.sum(axis=1).astype(float)
        self.row_diagnostics_ = pd.DataFrame(index=df.index)
        for column, flag in hard_by_column.items():
            if flag.any():
                self.row_diagnostics_[f"hard_invalid__{column}"] = flag
        for column, flag in soft_by_column.items():
            if flag.any():
                self.row_diagnostics_[f"soft_warning__{column}"] = flag
        self.validation_report_ = {
            column: int(values.sum())
            for column, values in self.row_diagnostics_.items()
        }
        return df

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return self.feature_names_out_.copy()


class CreditFeatureEngineer(TransformerMixin, BaseEstimator):
    """Create point-in-time-assumed, leakage-free features from cleaned inputs."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fit(self, X: pd.DataFrame, y: Any = None) -> "CreditFeatureEngineer":
        frame = _require_frame(X)
        excluded = set(self.config["leakage_columns"])
        dependencies = set().union(*DERIVED_FEATURE_DEPENDENCIES.values())
        leaked = dependencies & excluded
        if leaked:
            raise ValueError(f"Derived features depend on leakage columns: {sorted(leaked)}")
        base = [
            column
            for column in self.config["predictive_pipeline"]["required_predictors"]
            if column
            not in self.config["predictive_pipeline"]["drop_after_derivation"]
        ]
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.feature_names_out_ = np.asarray(
            base + list(DERIVED_FEATURE_DEPENDENCIES), dtype=object
        )
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not hasattr(self, "feature_names_out_"):
            raise RuntimeError("CreditFeatureEngineer must be fitted before transform")
        df = _require_frame(X).copy(deep=True)
        salary = df["salario_cliente"].where(df["salario_cliente"] > 0)
        capital = df["capital_prestado"].where(df["capital_prestado"] > 0)
        accounts = df["cant_creditosvigentes"].replace(0, np.nan)
        calc = pd.DataFrame(index=df.index)

        calc["calc_ratio_cuota_salario"] = df["cuota_pactada"] / salary
        calc["calc_ratio_pagos_otros_salario"] = (
            df["total_otros_prestamos"] / salary
        )
        calc["calc_ratio_capital_salario"] = df["capital_prestado"] / salary
        calc["calc_carga_financiera_total"] = (
            df["cuota_pactada"] + df["total_otros_prestamos"]
        ) / salary
        calc["calc_cuota_sobre_capital"] = df["cuota_pactada"] / capital
        calc["calc_cobertura_cuotas"] = (
            df["cuota_pactada"] * df["plazo_meses"] / capital
        )
        calc["calc_log_capital"] = np.log10(capital)

        calc["calc_intensidad_consulta"] = df["huella_consulta"] / (
            df["cant_creditosvigentes"] + 1
        )
        adult_years = (df["edad_cliente"] - 18).clip(lower=1)
        calc["calc_creditos_por_anio_adulto"] = (
            df["cant_creditosvigentes"] / adult_years
        )
        sectors = [
            "creditos_sectorFinanciero",
            "creditos_sectorCooperativo",
            "creditos_sectorReal",
        ]
        calc["calc_share_sector_financiero"] = df[sectors[0]] / accounts
        calc["calc_share_sector_real"] = df[sectors[2]] / accounts
        calc["calc_share_sector_cooperativo"] = df[sectors[1]] / accounts
        complete_sectors = df[sectors].notna().all(axis=1)
        calc["calc_sectores_distintos"] = (
            (df[sectors] > 0).sum(axis=1).where(complete_sectors)
        )
        sector_sum = df[sectors].sum(axis=1, min_count=len(sectors))
        calc["calc_creditos_no_reportados"] = (
            df["cant_creditosvigentes"] - sector_sum
        )

        calc["calc_tiene_mora"] = (df["saldo_mora"] > 0).astype(float).where(
            df["saldo_mora"].notna()
        )
        calc["calc_ratio_mora_saldo"] = (
            df["saldo_mora"] / df["saldo_total"].replace(0, np.nan)
        )
        calc["calc_interes_devengado"] = (
            df["saldo_total"] - df["saldo_principal"]
        )
        calc["calc_saldo_por_credito"] = df["saldo_total"] / accounts
        calc["calc_ratio_saldo_capital"] = df["saldo_total"] / capital

        bureau_income = df["promedio_ingresos_datacredito"]
        calc["calc_desfase_ingresos"] = bureau_income / salary
        both_incomes = salary.notna() & bureau_income.notna()
        calc["calc_ingreso_declarado_mayor"] = (salary > bureau_income).astype(
            float
        ).where(both_incomes)
        calc["calc_sin_info_ingresos_bureau"] = bureau_income.isna().astype(float)
        calc["calc_sin_score_bureau"] = df["puntaje_datacredito"].isna().astype(
            float
        )
        calc["calc_n_reglas_violadas"] = df[INTERNAL_RULE_COUNT]
        calc = calc.replace([np.inf, -np.inf], np.nan)

        drop = self.config["predictive_pipeline"]["drop_after_derivation"]
        base = df.drop(columns=drop + [INTERNAL_RULE_COUNT], errors="ignore")
        result = pd.concat([base, calc], axis=1)
        return result.loc[:, self.feature_names_out_].copy()

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return self.feature_names_out_.copy()


class DataFrameImputer(TransformerMixin, BaseEstimator):
    """Fit training medians and explicit categorical missing values."""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def fit(self, X: pd.DataFrame, y: Any = None) -> "DataFrameImputer":
        frame = _require_frame(X)
        settings = self.config["predictive_pipeline"]["imputation"]
        categorical = self.config["predictive_pipeline"]["categorical_predictors"]
        self.feature_names_in_ = np.asarray(frame.columns, dtype=object)
        self.categorical_columns_ = [
            column for column in categorical if column in frame.columns
        ]
        self.numeric_columns_ = [
            column for column in frame.columns if column not in self.categorical_columns_
        ]
        self.fill_values_: dict[str, float | str] = {}
        self.all_missing_numeric_: list[str] = []
        for column in self.numeric_columns_:
            median = pd.to_numeric(frame[column], errors="coerce").median()
            if pd.isna(median):
                median = float(settings["all_missing_numeric_fallback"])
                self.all_missing_numeric_.append(column)
            self.fill_values_[column] = float(median)
        for column in self.categorical_columns_:
            self.fill_values_[column] = settings["categorical_fill_value"]

        prefix = settings["missing_indicator_prefix"]
        output = list(frame.columns) + [f"{prefix}{column}" for column in frame.columns]
        self.feature_names_out_ = np.asarray(output, dtype=object)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        if not hasattr(self, "fill_values_"):
            raise RuntimeError("DataFrameImputer must be fitted before transform")
        frame = _require_frame(X)
        expected = list(self.feature_names_in_)
        missing = [column for column in expected if column not in frame.columns]
        if missing:
            raise ValueError(f"Missing engineered feature columns: {missing}")
        df = frame.loc[:, expected].copy(deep=True)
        prefix = self.config["predictive_pipeline"]["imputation"][
            "missing_indicator_prefix"
        ]
        indicators = pd.DataFrame(
            {
                f"{prefix}{column}": df[column].isna().astype("int8")
                for column in expected
            },
            index=df.index,
        )
        for column in self.numeric_columns_:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(
                self.fill_values_[column]
            )
        for column in self.categorical_columns_:
            df[column] = df[column].astype("string").fillna(
                str(self.fill_values_[column])
            )
        result = pd.concat([df, indicators], axis=1)
        return result.loc[:, self.feature_names_out_]

    def get_feature_names_out(self, input_features: Any = None) -> np.ndarray:
        return self.feature_names_out_.copy()


def build_data_preparation_pipeline(
    config: dict[str, Any] | None = None,
) -> Pipeline:
    """Build the shared predictor pipeline; fit it on training rows only."""
    cfg = config or load_config()
    return Pipeline(
        steps=[
            ("select", PredictorSelector(cfg)),
            ("clean", CreditDataCleaner(cfg)),
            ("validate", CreditDataValidator(cfg)),
            ("derive_features", CreditFeatureEngineer(cfg)),
            ("impute", DataFrameImputer(cfg)),
        ]
    )


def get_pipeline_diagnostics(
    pipeline: Pipeline, dataset: CreditDataset | None = None
) -> dict[str, Any]:
    """Return serializable diagnostics from the most recent transformation."""
    cfg = pipeline.named_steps["select"].config
    ignored = (
        dataset.ignored_columns
        if dataset is not None
        else getattr(pipeline.named_steps["select"], "ignored_columns_", ())
    )
    excluded = (
        dataset.excluded_columns_present
        if dataset is not None
        else getattr(
            pipeline.named_steps["select"], "excluded_columns_present_", ()
        )
    )
    return {
        "schema_version": cfg["predictive_pipeline"]["schema_version"],
        "ignored_columns": list(ignored),
        "excluded_columns_present": list(excluded),
        "cleaning": getattr(
            pipeline.named_steps["clean"], "validation_report_", {}
        ),
        "validation": getattr(
            pipeline.named_steps["validate"], "validation_report_", {}
        ),
        "all_missing_numeric_fallbacks": list(
            getattr(pipeline.named_steps["impute"], "all_missing_numeric_", ())
        ),
        "feature_count": len(pipeline.get_feature_names_out()),
    }


def fit_prepare_training(
    raw: pd.DataFrame, config: dict[str, Any] | None = None
) -> tuple[CreditDataset, Pipeline]:
    """Fit on an already-selected training partition and return separated output."""
    cfg = config or load_config()
    dataset = extract_dataset(raw, cfg, require_target=True)
    pipeline = build_data_preparation_pipeline(cfg)
    predictors = pipeline.fit_transform(dataset.predictors)
    prepared = CreditDataset(
        predictors=predictors,
        target=dataset.target,
        metadata=dataset.metadata,
        ignored_columns=dataset.ignored_columns,
        excluded_columns_present=dataset.excluded_columns_present,
    )
    return prepared, pipeline


def transform_for_prediction(
    raw: pd.DataFrame,
    pipeline: Pipeline,
    config: dict[str, Any] | None = None,
) -> CreditDataset:
    """Apply a fitted training pipeline to validation, test, or live records."""
    cfg = config or pipeline.named_steps["select"].config
    dataset = extract_dataset(raw, cfg)
    return CreditDataset(
        predictors=pipeline.transform(dataset.predictors),
        target=dataset.target,
        metadata=dataset.metadata,
        ignored_columns=dataset.ignored_columns,
        excluded_columns_present=dataset.excluded_columns_present,
    )


def split_and_prepare(
    raw: pd.DataFrame,
    config: dict[str, Any] | None = None,
    *,
    train_fraction: float | None = None,
) -> tuple[PreparedCreditSplit, Pipeline]:
    """Chronologically split raw rows, fit on train, and transform both partitions."""
    cfg = config or load_config()
    raw_split = chronological_train_test_split(
        raw, cfg, train_fraction=train_fraction
    )
    train, pipeline = fit_prepare_training(raw_split.train, cfg)
    train_diagnostics = get_pipeline_diagnostics(pipeline, train)
    test = transform_for_prediction(raw_split.test, pipeline, cfg)
    if test.target is None:
        raise ValueError("The test partition must include the target for evaluation")
    test_diagnostics = get_pipeline_diagnostics(pipeline, test)
    prepared = PreparedCreditSplit(
        train=train,
        test=test,
        summary=raw_split.summary,
        train_diagnostics=train_diagnostics,
        test_diagnostics=test_diagnostics,
    )
    return prepared, pipeline


def read_raw_data(
    config: dict[str, Any] | None = None,
    input_path: str | Path | None = None,
    config_dir: str | Path = DEFAULT_CONFIG_PATH.parent,
) -> pd.DataFrame:
    """Read the source extract without allowing pandas to infer missing values."""
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


def _write_dataset(
    dataset: CreditDataset,
    output: Path,
    target_output: Path | None,
    metadata_output: Path | None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.predictors.to_csv(output, index=False)
    if target_output is not None and dataset.target is not None:
        target_output.parent.mkdir(parents=True, exist_ok=True)
        dataset.target.to_csv(target_output, index=False)
    if metadata_output is not None:
        metadata_output.parent.mkdir(parents=True, exist_ok=True)
        dataset.metadata.to_csv(metadata_output, index=False)


def _write_diagnostics(report: dict[str, Any], path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare credit predictors")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fit_parser = subparsers.add_parser("fit", help="Fit on a training partition")
    fit_parser.add_argument("--input", type=Path)
    fit_parser.add_argument("--output", type=Path, required=True)
    fit_parser.add_argument("--target-output", type=Path, required=True)
    fit_parser.add_argument("--metadata-output", type=Path)
    fit_parser.add_argument("--artifact", type=Path, required=True)
    fit_parser.add_argument("--diagnostics-output", type=Path)

    split_parser = subparsers.add_parser(
        "split-fit", help="Create a chronological 70/30 split and fit on train"
    )
    split_parser.add_argument("--input", type=Path)
    split_parser.add_argument("--train-output", type=Path, required=True)
    split_parser.add_argument("--test-output", type=Path, required=True)
    split_parser.add_argument("--train-target-output", type=Path, required=True)
    split_parser.add_argument("--test-target-output", type=Path, required=True)
    split_parser.add_argument("--train-metadata-output", type=Path)
    split_parser.add_argument("--test-metadata-output", type=Path)
    split_parser.add_argument("--artifact", type=Path, required=True)
    split_parser.add_argument("--diagnostics-output", type=Path)
    split_parser.add_argument("--train-fraction", type=float)

    transform_parser = subparsers.add_parser(
        "transform", help="Transform with a fitted training artifact"
    )
    transform_parser.add_argument("--input", type=Path, required=True)
    transform_parser.add_argument("--output", type=Path, required=True)
    transform_parser.add_argument("--target-output", type=Path)
    transform_parser.add_argument("--metadata-output", type=Path)
    transform_parser.add_argument("--artifact", type=Path, required=True)
    transform_parser.add_argument("--diagnostics-output", type=Path)
    args = parser.parse_args()

    cfg = load_config(args.config)
    raw = read_raw_data(cfg, args.input, args.config.parent)
    if args.command == "split-fit":
        split, pipeline = split_and_prepare(
            raw, cfg, train_fraction=args.train_fraction
        )
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, args.artifact)
        _write_dataset(
            split.train,
            args.train_output,
            args.train_target_output,
            args.train_metadata_output,
        )
        _write_dataset(
            split.test,
            args.test_output,
            args.test_target_output,
            args.test_metadata_output,
        )
        _write_diagnostics(
            {
                "split": split.summary,
                "train": split.train_diagnostics,
                "test": split.test_diagnostics,
            },
            args.diagnostics_output,
        )
        print(
            f"Prepared train {len(split.train.predictors):,} rows and test "
            f"{len(split.test.predictors):,} rows with "
            f"{split.train.predictors.shape[1]} predictors"
        )
        return
    if args.command == "fit":
        dataset, pipeline = fit_prepare_training(raw, cfg)
        args.artifact.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, args.artifact)
    else:
        pipeline = joblib.load(args.artifact)
        dataset = transform_for_prediction(raw, pipeline)

    _write_dataset(
        dataset,
        args.output,
        getattr(args, "target_output", None),
        args.metadata_output,
    )
    _write_diagnostics(
        get_pipeline_diagnostics(pipeline, dataset), args.diagnostics_output
    )
    print(
        f"Prepared {len(dataset.predictors):,} rows and "
        f"{dataset.predictors.shape[1]} predictors -> {args.output}"
    )


if __name__ == "__main__":
    # Use canonically imported classes so CLI-created joblib artifacts can be loaded
    # later by a modelling process that imports this module.
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from mlops_pipeline.src.ft_engineering import main as canonical_main

    canonical_main()

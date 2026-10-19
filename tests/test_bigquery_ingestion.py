from __future__ import annotations

from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from mlops_pipeline.src.ft_engineering import (
    read_raw_data,
    read_raw_data_from_bigquery,
)


def test_read_raw_data_from_bigquery_formats_dataframe():
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    sample_df = pd.DataFrame({
        "tipo_credito": [4, 9],
        "fecha_prestamo": pd.to_datetime(["2025-01-01 14:00", "2025-02-01 10:00"]),
        "capital_prestado": [1000000, 2000000],
        "puntaje": ["95,22", None],
        "Pago_atiempo": [1, 0],
    })
    mock_query_job.to_dataframe.return_value = sample_df
    mock_client.query.return_value = mock_query_job

    df = read_raw_data_from_bigquery(
        project_id="test-proj",
        dataset_id="test-ds",
        table_id="test-tbl",
        client=mock_client,
    )

    assert df.shape == (2, 5)
    assert df["fecha_prestamo"].tolist() == ["01/01/2025 14:00", "01/02/2025 10:00"]
    assert df["puntaje"].tolist() == ["95,22", ""]
    assert all(pd.api.types.is_string_dtype(df[col]) or df[col].dtype == object for col in df.columns)
    mock_client.query.assert_called_once_with(
        "SELECT * FROM `test-proj.test-ds.test-tbl`"
    )


def test_read_raw_data_dispatches_to_bigquery_via_uri():
    with patch(
        "mlops_pipeline.src.ft_engineering.read_raw_data_from_bigquery"
    ) as mock_bq_reader:
        mock_bq_reader.return_value = pd.DataFrame({"dummy": ["1"]})
        result = read_raw_data(input_path="bq://my-proj.my-ds.my-table")
        assert result.shape == (1, 1)
        mock_bq_reader.assert_called_once()
        _, kwargs = mock_bq_reader.call_args
        assert kwargs["project_id"] == "my-proj"
        assert kwargs["dataset_id"] == "my-ds"
        assert kwargs["table_id"] == "my-table"


def test_read_raw_data_dispatches_when_use_bigquery_flag_is_true():
    with patch(
        "mlops_pipeline.src.ft_engineering.read_raw_data_from_bigquery"
    ) as mock_bq_reader:
        mock_bq_reader.return_value = pd.DataFrame({"col": ["val"]})
        result = read_raw_data(use_bigquery=True)
        assert result.shape == (1, 1)
        mock_bq_reader.assert_called_once()


def test_cli_load_data_with_bigquery_flag(capsys):
    from mlops_pipeline.src.load_data import main as load_data_main

    with patch(
        "mlops_pipeline.src.load_data.read_raw_data"
    ) as mock_read:
        mock_read.return_value = pd.DataFrame({"col1": [1, 2]})
        load_data_main(["--bigquery"])
        mock_read.assert_called_once()
        _, kwargs = mock_read.call_args
        assert kwargs.get("use_bigquery") is True


def test_cli_ft_engineering_split_fit_with_bigquery_flag(tmp_path):
    from mlops_pipeline.src.ft_engineering import main as ft_main

    train_out = tmp_path / "train.csv"
    val_out = tmp_path / "val.csv"
    art_out = tmp_path / "pipeline.joblib"

    with patch("mlops_pipeline.src.ft_engineering.read_raw_data") as mock_read, patch(
        "mlops_pipeline.src.ft_engineering.split_and_prepare"
    ) as mock_split, patch("joblib.dump"):
        mock_read.return_value = pd.DataFrame({"dummy": [1]})
        mock_split.return_value = (
            MagicMock(
                train=MagicMock(predictors=pd.DataFrame({"x": [1]}), metadata=pd.DataFrame(), target=pd.Series([1])),
                test=MagicMock(predictors=pd.DataFrame({"x": [2]}), metadata=pd.DataFrame(), target=pd.Series([0])),
                summary={},
                train_diagnostics={},
                test_diagnostics={},
            ),
            MagicMock(),
        )

        with patch("mlops_pipeline.src.ft_engineering.write_partition_to_bigquery") as mock_write_part, patch(
            "mlops_pipeline.src.ft_engineering.write_dataframe_to_bigquery"
        ) as mock_write_df, patch(
            "mlops_pipeline.src.ft_engineering.chronological_train_test_split"
        ) as mock_raw_split:
            mock_raw_split.return_value = MagicMock(train=pd.DataFrame(), test=pd.DataFrame())
            ft_main([
                "split-fit",
                "--bigquery",
                "--train-output",
                str(train_out),
                "--validation-output",
                str(val_out),
                "--artifact",
                str(art_out),
            ])
            mock_read.assert_called_once()
            _, kwargs = mock_read.call_args
            assert kwargs.get("use_bigquery") is True
            assert mock_write_part.call_count == 2
            assert mock_write_df.call_count == 2


def test_write_and_read_partition_bigquery():
    from mlops_pipeline.src.ft_engineering import (
        write_dataframe_to_bigquery,
        write_partition_to_bigquery,
        read_partition_from_bigquery,
        CreditDataset,
    )

    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_client.load_table_from_dataframe.return_value = mock_job

    df = pd.DataFrame({"feat1": [1, 2]})
    res = write_dataframe_to_bigquery(
        df,
        table_id="my_tbl",
        project_id="my-proj",
        dataset_id="my-ds",
        client=mock_client,
    )
    assert res == "my-proj.my-ds.my_tbl"
    mock_client.load_table_from_dataframe.assert_called_once()

    # Test write_partition_to_bigquery
    dataset = CreditDataset(
        predictors=pd.DataFrame({"x1": [10, 20]}),
        target=pd.Series([1, 0], name="Pago_atiempo"),
        metadata=pd.DataFrame({"dt": ["2025-01-01", "2025-01-02"]}),
    )
    part_res = write_partition_to_bigquery(
        dataset,
        table_id="part_tbl",
        project_id="my-proj",
        dataset_id="my-ds",
        client=mock_client,
    )
    assert part_res == "my-proj.my-ds.part_tbl"

    # Test read_partition_from_bigquery
    mock_query_job = MagicMock()
    mock_query_job.to_dataframe.return_value = pd.DataFrame({"col": [1]})
    mock_client.query.return_value = mock_query_job

    read_df = read_partition_from_bigquery(
        table_id="part_tbl",
        project_id="my-proj",
        dataset_id="my-ds",
        client=mock_client,
    )
    assert read_df.shape == (1, 1)
    mock_client.query.assert_called_once_with("SELECT * FROM `my-proj.my-ds.part_tbl`")


def test_cli_model_training_evaluation_with_bigquery_flag(tmp_path):
    from mlops_pipeline.src.model_training_evaluation import main as model_main

    out_dir = tmp_path / "out"

    with patch("mlops_pipeline.src.model_training_evaluation.read_raw_data") as mock_read, patch(
        "mlops_pipeline.src.model_training_evaluation.train_and_evaluate"
    ) as mock_train:
        mock_read.return_value = pd.DataFrame({"dummy": [1]})
        mock_train.return_value = MagicMock(artifact_paths={})

        model_main([
            "--bigquery",
            "--smoke",
            "--output-dir",
            str(out_dir),
        ])
        mock_read.assert_called_once()
        _, kwargs = mock_read.call_args
        assert kwargs.get("use_bigquery") is True




"""Static contract checks for the CPU-oriented training notebook."""

import json
from pathlib import Path


NOTEBOOK = (
    Path(__file__).parents[1]
    / "etl_scripts"
    / "src"
    / "development"
    / "model_training.ipynb"
)


def test_training_notebook_is_clean_and_uses_shared_pipeline_contract():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert notebook["cells"]
    cell_ids = [cell["id"] for cell in notebook["cells"]]
    assert len(cell_ids) == len(set(cell_ids))
    code = "\n".join(
        "".join(cell.get("source", []))
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )
    assert "build_model(" in code
    assert "summarize_classification(" in code
    assert "train_and_evaluate(" in code
    assert "device='cpu'" in code
    assert "chronological_train_test_split(" in code
    assert "holdout_predictions.csv" in code
    assert "selection['model']" in code
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["execution_count"] is None
            assert cell["outputs"] == []


def test_training_notebook_defaults_to_smoke_and_writes_only_ignored_runs():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )
    assert "CDP_NOTEBOOK_PROFILE', 'smoke'" in source
    assert "repository_root / 'runs'" in source
    assert "output_dir / 'selection.json'" in source
    assert "output_dir / 'figures'" in source

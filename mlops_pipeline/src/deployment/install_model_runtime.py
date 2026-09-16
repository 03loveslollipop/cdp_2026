"""Install only the runtime needed by the configured winning model family."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


FAMILY_REQUIREMENTS = {
    "logistic_regression": [],
    "decision_tree": [],
    "gaussian_nb": [],
    "random_forest": [],
    "extra_trees": [],
    "svm": [],
    "xgboost": ["xgboost-cpu==3.4.1"],
    "lightgbm": ["lightgbm==4.7.0"],
    "pytorch_mlp": ["torch==2.11.0"],
}
DEPLOYMENT_CONFIG_PATH = Path(__file__).with_name("deployment_model_config.json")


def main() -> None:
    family = json.loads(
        DEPLOYMENT_CONFIG_PATH.read_text(encoding="utf-8")
    )["model_family"]
    if family not in FAMILY_REQUIREMENTS:
        raise SystemExit(f"Unsupported deployment model family: {family}")
    requirements = FAMILY_REQUIREMENTS[family]
    if requirements:
        command = [sys.executable, "-m", "pip", "install", "--no-cache-dir"]
        if family == "pytorch_mlp":
            command.extend(["--index-url", "https://download.pytorch.org/whl/cpu"])
        subprocess.run(command + requirements, check=True)


if __name__ == "__main__":
    main()

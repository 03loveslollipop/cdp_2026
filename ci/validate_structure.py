"""Fail early if the cloned credit repository is incomplete or unsafe to model."""
import json
from pathlib import Path


def validate(root=Path('.')):
    required = [
        'README.md', 'database.csv', 'config.json', 'requirements-ci.txt',
        'Jenkinsfile', 'tests', 'ci/training.json', 'ci/quality-gates.json',
        'mlops_pipeline/src/ft_engineering.py',
        'mlops_pipeline/src/model_training_evaluation.py',
    ]
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        raise ValueError(f'Missing required repository paths: {missing}')
    config = json.loads((root / 'config.json').read_text())
    predictive = config['predictive_pipeline']
    forbidden = set(config['leakage_columns']) | {config['schema']['target']}
    if forbidden.intersection(predictive['required_predictors']):
        raise ValueError('Target or outcome-derived columns appear in predictors')
    if predictive['train_test_split']['strategy'] != 'chronological':
        raise ValueError('Credit exercise requires chronological splits')
    print(f'Structure OK: {len(required)} required paths; chronological split; no target leakage')


if __name__ == '__main__':
    validate()

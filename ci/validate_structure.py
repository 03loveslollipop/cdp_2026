"""Fail early if the cloned credit repository is incomplete or unsafe to model."""
import argparse
import json
from pathlib import Path


def validate(root=Path('.'), *, mode='full', ci_files=True):
    required = ['README.md', 'tests']
    if mode == 'full':
        required += ['mlops_pipeline/src', 'database.csv', 'config.json', 'mlops_pipeline/src/ft_engineering.py',
                     'mlops_pipeline/src/model_training_evaluation.py']
    if ci_files:
        required += ['requirements-ci.txt', 'Jenkinsfile', 'ci/training.json', 'ci/quality-gates.json']
    missing = [name for name in required if not (root / name).exists()]
    if missing:
        raise ValueError(f'Missing required repository paths: {missing}')
    if mode == 'tests':
        print(f'Structure OK: {len(required)} source paths; branch tests only')
        return
    config = json.loads((root / 'config.json').read_text())
    predictive = config['predictive_pipeline']
    forbidden = set(config['leakage_columns']) | {config['schema']['target']}
    if forbidden.intersection(predictive['required_predictors']):
        raise ValueError('Target or outcome-derived columns appear in predictors')
    if predictive['train_test_split']['strategy'] != 'chronological':
        raise ValueError('Credit exercise requires chronological splits')
    print(f'Structure OK: {len(required)} required paths; chronological split; no target leakage')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['tests', 'full'], default='full')
    parser.add_argument('--without-ci-files', action='store_true')
    args = parser.parse_args()
    validate(mode=args.mode, ci_files=not args.without_ci_files)

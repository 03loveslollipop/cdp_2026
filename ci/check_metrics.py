"""Gate the training-selected model using temporal validation, never test tuning."""
import argparse
import csv
import json
import math
from pathlib import Path


def check(run_dir, policy_path=Path('ci/quality-gates.json')):
    run_dir = Path(run_dir)
    selected = json.loads((run_dir / 'selection.json').read_text())['model']
    policy = json.loads(Path(policy_path).read_text())
    with (run_dir / 'validation_summary.csv').open() as handle:
        matches = [row for row in csv.DictReader(handle) if row['model'] == selected]
    if len(matches) != 1 or selected in {'heuristic', 'dummy'}:
        raise ValueError('Exactly one learned, training-selected model is required')
    row = matches[0]
    rules = [
        ('mean_f1', 'minimum_validation_f1', True),
        ('mean_roc_auc', 'minimum_validation_roc_auc', True),
        ('temporal_f1_std', 'maximum_temporal_f1_std', False),
        ('seed_f1_std', 'maximum_seed_f1_std', False),
    ]
    results = []
    for metric, limit_name, minimum in rules:
        value, limit = float(row[metric]), float(policy[limit_name])
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f'Invalid {metric}: {value}')
        if not math.isfinite(limit) or not 0 <= limit <= 1:
            raise ValueError(f'Invalid policy {limit_name}: {limit}')
        passed = value >= limit if minimum else value <= limit
        results.append(dict(metric=metric, value=value, limit=limit, passed=passed))
    report = dict(model=selected, passed=all(r['passed'] for r in results), checks=results)
    (run_dir / 'quality-gate.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    if not report['passed']:
        raise ValueError('Model quality/stability gate failed')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--policy', type=Path, default=Path('ci/quality-gates.json'))
    args = parser.parse_args()
    check(args.run_dir, args.policy)

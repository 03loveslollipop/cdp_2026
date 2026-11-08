"""Score downloaded dashboard outputs and compare only matching frozen holdouts."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score

from cloud.prepare_data import frame_hash
from mlops_pipeline.src.ft_engineering import chronological_train_test_split, read_raw_data
from mlops_pipeline.src.model_training_evaluation import summarize_classification


def uncertainty(target, probability, threshold, repeats=200):
    """Stratified bootstrap intervals, conditional on the observed class prevalence."""
    target, probability = np.asarray(target), np.asarray(probability)
    generator = np.random.default_rng(20261108)
    groups = [np.flatnonzero(target == label) for label in (0, 1)]
    scores = {name: [] for name in ['accuracy', 'default_f1', 'roc_auc']}
    for _ in range(repeats):
        index = np.concatenate([generator.choice(group, len(group), replace=True) for group in groups])
        y, p = target[index], probability[index]
        predicted = np.where(p >= threshold, 0, 1)
        scores['accuracy'].append(accuracy_score(y, predicted))
        scores['default_f1'].append(f1_score(y, predicted, pos_label=0, zero_division=0))
        scores['roc_auc'].append(roc_auc_score(y == 0, p))
    return {name: np.quantile(values, [0.025, 0.975]).tolist() for name, values in scores.items()}


def normalize_local(run, output, origin='python-local'):
    run = Path(run)
    manifest = json.loads((run / 'manifest.json').read_text())
    model = json.loads((run / 'selection.json').read_text())['model']
    metrics = pd.read_csv(run / 'holdout_summary.csv').set_index('model').loc[model].to_dict()
    metrics['confusion_matrix'] = json.loads(metrics['confusion_matrix'])
    validation = pd.read_csv(run / 'validation_summary.csv').set_index('model').loc[model]
    raw = read_raw_data().reset_index(drop=True)
    if frame_hash(raw) != manifest['dataset_sha256']:
        raise ValueError('Local source no longer matches this benchmark')
    predictions = pd.read_csv(run / 'holdout_predictions.csv')
    predictions = predictions.loc[predictions.model == model].sort_values('row_id')
    report = {
        'origin': origin, 'model': model,
        'dataset_sha256': manifest['dataset_sha256'],
        'holdout_sha256': frame_hash(chronological_train_test_split(raw).test),
        'metrics': metrics,
        'stability': {name: float(validation[name]) for name in ['mean_f1', 'temporal_f1_std', 'seed_f1_std']},
        'threshold_policy': 'Frozen temporal OOF threshold; positive class is default=0',
        'threshold': float(validation['threshold']),
        'confidence_intervals': uncertainty(predictions.target, predictions.default_probability,
                                             float(validation['threshold'])),
    }
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    return report


def score_automl(prediction_paths, data, output):
    data = Path(data)
    manifest = json.loads((data / 'manifest.json').read_text())
    labels = pd.read_csv(data / 'holdout-labels.csv', dtype={'row_id': str})
    records = []
    for path in prediction_paths:
        for line in Path(path).read_text().splitlines():
            item = json.loads(line)
            if item.get('error'):
                raise ValueError(f'AutoML returned an error: {item["error"]}')
            key = item.get('key', item.get('instance', {}).get('row_id'))
            if key is None:
                raise ValueError('Prediction has no row_id/key; never assume output order')
            prediction = item['prediction']
            classes, scores = list(map(str, prediction['classes'])), prediction['scores']
            if set(classes) != {'0', '1'} or len(classes) != 2 or len(scores) != 2:
                raise ValueError('Expected exactly the two Pago_atiempo classes')
            values = np.asarray(scores, dtype=float)
            if not np.isfinite(values).all() or not np.isclose(values.sum(), 1, atol=1e-4):
                raise ValueError('Malformed AutoML class probabilities')
            records.append({'row_id': str(key), 'probability': float(values[classes.index('0')])})
    predictions = pd.DataFrame(records, columns=['row_id', 'probability'])
    if predictions.row_id.duplicated().any() or set(predictions.row_id) != set(labels.row_id):
        raise ValueError('Missing, extra or duplicate prediction row IDs')
    joined = labels.merge(predictions, on='row_id', validate='one_to_one')
    # Fixed documented operating point: no threshold search on final holdout.
    threshold = 0.5
    predicted = np.where(joined.probability >= threshold, 0, 1)
    metrics = summarize_classification(joined.target, predicted, joined.probability)
    blocks = []
    for block in np.array_split(np.arange(len(joined)), 3):
        subset = joined.iloc[block]
        if subset.target.nunique() == 2:
            blocks.append(summarize_classification(subset.target,
                          np.where(subset.probability >= threshold, 0, 1), subset.probability))
    report = {
        'origin': 'vertex-automl', 'model': 'automl-tabular',
        'dataset_sha256': manifest['dataset_sha256'], 'holdout_sha256': manifest['holdout_sha256'],
        'metrics': metrics, 'threshold': threshold,
        'threshold_policy': 'Fixed default probability >= 0.5; no holdout threshold tuning',
        'stability': {'holdout_time_blocks': blocks, 'seed_f1_std': None,
                      'note': 'Single AutoML run: repeat-training stability remains unmeasured'},
        'confidence_intervals': uncertainty(joined.target, joined.probability, threshold),
    }
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    return report


def compare(paths, output, language='en'):
    reports = [json.loads(Path(path).read_text()) for path in paths]
    if len({(r['dataset_sha256'], r['holdout_sha256']) for r in reports}) != 1:
        raise ValueError('Cannot compare different datasets or holdout partitions')
    if len({r['origin'] for r in reports}) != len(reports):
        raise ValueError('Duplicate model origins would obscure the comparison')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    columns = ['accuracy', 'default_f1', 'roc_auc', 'average_precision']
    rows = [{'origin': r['origin'], 'model': r['model'], **{m: r['metrics'][m] for m in columns},
             'temporal_f1_std': r['stability'].get('temporal_f1_std'),
             'seed_f1_std': r['stability'].get('seed_f1_std')} for r in reports]
    frame = pd.DataFrame(rows)
    frame.to_csv(output / 'comparison.csv', index=False)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    labels = {'python-local': 'Python local', 'vertex-custom': 'Vertex CPU',
              'vertex-automl': 'AutoML'} if language == 'es' else {}
    metric_labels = {'accuracy': 'Exactitud', 'default_f1': 'F1 de incumplimiento',
                     'roc_auc': 'ROC-AUC'} if language == 'es' else {}
    for axis, name in zip(axes, columns[:3]):
        for position, report in enumerate(reports):
            value = report['metrics'][name]
            axis.bar(position, value, color=['#2864b4', '#21856a', '#bb7730'][position % 3])
            interval = report.get('confidence_intervals', {}).get(name)
            if interval:
                # Quantile intervals can miss the point estimate slightly on discrete metrics.
                low, high = min(value, interval[0]), max(value, interval[1])
                axis.errorbar(position, value, yerr=[[value-low], [high-value]], color='black', capsize=4)
        axis.set(title=metric_labels.get(name, name), ylim=(0, 1), xticks=range(len(reports)),
                 xticklabels=[labels.get(r['origin'], r['origin']) for r in reports])
        axis.tick_params(axis='x', labelrotation=20)
    fig.suptitle('Resultados medidos sobre el mismo holdout (incumplimiento = 0)'
                 if language == 'es' else 'Measured frozen-holdout results (default = 0)')
    fig.savefig(output / 'comparison.png', dpi=160)
    plt.close(fig)
    present = {r['origin'] for r in reports}
    pending = sorted({'vertex-custom', 'vertex-automl'} - present)
    header = '| Origin | Model | Accuracy | Default F1 | ROC-AUC | PR-AUC |'
    lines = [header, '|---|---|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| ' + ' | '.join([row['origin'], row['model']] + [f'{row[m]:.4f}' for m in columns]) + ' |')
    text = '# Credit model comparison\n\n' + '\n'.join(lines) + '\n\n'
    text += f'Pending dashboard runs: {", ".join(pending) if pending else "none"}.\n\n'
    text += ('The same source and frozen holdout fingerprints are required. Default is label 0. '
             'Accuracy must be read alongside default F1 and PR-AUC because defaults are rare. '
             'Bootstrap intervals condition on the observed class mix; they do not measure retraining variance. '
             'Python/custom use OOF-calibrated thresholds; AutoML uses a fixed 0.5 threshold, so F1 compares operating '
             'policies as well as fitted models. ROC-AUC and PR-AUC compare rankings.\n\n'
             'Python training exposes preprocessing, calibration, temporal folds, seeds and runtime costs. '
             'AutoML reduces manual model-search work and provides managed evaluation, while offering less control '
             'over search internals and incurring a training budget. No tool is declared superior before cloud results exist.\n\n'
             'Stability requires temporal and seed variation. Three seeds and temporal folds are available for Python/custom; '
             'one AutoML run only supports holdout bootstrap/time-block analysis. Repeated dashboard training with the '
             'same split and budget is needed before claiming AutoML repeatability. The historical holdout was already '
             'examined during EDA and is not fresh external validation.\n\n![Measured comparison](comparison.png)\n')
    (output / 'README.md').write_text(text)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    local = subs.add_parser('local')
    local.add_argument('--run', required=True)
    local.add_argument('--output', required=True)
    local.add_argument('--origin', default='python-local')
    automl = subs.add_parser('automl')
    automl.add_argument('--predictions', nargs='+', required=True)
    automl.add_argument('--data', required=True)
    automl.add_argument('--output', required=True)
    report = subs.add_parser('report')
    report.add_argument('--inputs', nargs='+', required=True)
    report.add_argument('--output', required=True)
    report.add_argument('--language', choices=['en', 'es'], default='en')
    args = parser.parse_args()
    if args.command == 'local':
        normalize_local(args.run, args.output, args.origin)
    elif args.command == 'automl':
        score_automl(args.predictions, args.data, args.output)
    else:
        compare(args.inputs, args.output, args.language)

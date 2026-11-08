"""Normalize downloaded AutoML evaluation without submitting paid predictions.

Use the default-class slice at a fixed 0.5 threshold. Overall micro metrics and
native PR-AUC remain separately labeled; native PR-AUC is not sklearn AP.
"""
import argparse
import json
import math
from pathlib import Path


def resource_without_version(name):
    return name.split('@', 1)[0]


def normalize(evaluation, slices, pipeline, dataset, model, manifest, input_uri):
    model_name = model['name']
    evaluation_parent, evaluation_id = evaluation['name'].split('/evaluations/')
    if resource_without_version(evaluation_parent) != model_name:
        raise ValueError('Evaluation belongs to a different model')
    if '@' in evaluation_parent and evaluation_parent.rsplit('@', 1)[1] != model.get('versionId'):
        raise ValueError('Evaluation belongs to a different model version')
    if model['trainingPipeline'] != pipeline['name'] or pipeline['state'] != 'PIPELINE_STATE_SUCCEEDED':
        raise ValueError('Model has no matching successful training pipeline')
    config = pipeline['inputDataConfig']
    if not dataset['name'].endswith('/datasets/' + config['datasetId']):
        raise ValueError('Training dataset does not match the downloaded dataset')
    if config.get('predefinedSplit', {}).get('key') != manifest['split_column']:
        raise ValueError('AutoML did not use the fixed manual partition')
    if dataset['metadata']['inputConfig']['gcsSource']['uri'] != [input_uri]:
        raise ValueError('Dataset source URI differs from the verified export')
    inputs = pipeline['trainingTaskInputs']
    features = [next(iter(t.values()))['columnName'] for t in inputs['transformations']]
    if (inputs['targetColumn'] != manifest['target'] or
            len(features) != len(set(features)) or set(features) != set(manifest['prediction_features'])):
        raise ValueError('Target or predictive columns differ from the manifest')
    if slices.get('nextPageToken'):
        raise ValueError('Download every evaluation-slice page')
    default = str(manifest['default_label'])
    candidates = [s for s in slices['modelEvaluationSlices']
                  if s['slice'] == {'dimension': 'annotationSpec', 'value': default}]
    if len(candidates) != 1:
        raise ValueError('A unique default-class evaluation slice is required')
    selected = candidates[0]
    parent, _ = selected['name'].split('/slices/')
    if (resource_without_version(parent.split('/evaluations/')[0]) != model_name or
            parent.split('/evaluations/')[1] != evaluation_id):
        raise ValueError('Class slice belongs to another evaluation')
    points = [p for p in selected['metrics']['confidenceMetrics']
              if math.isclose(p.get('confidenceThreshold', 0), 0.5, abs_tol=1e-9)]
    if len(points) != 1:
        raise ValueError('A unique native evaluation at threshold 0.5 is required')
    point = points[0]
    matrix = point['confusionMatrix']
    labels = [a['displayName'] for a in matrix['annotationSpecs']]
    if set(labels) != {'0', '1'} or len(labels) != 2:
        raise ValueError('Expected two display labels, not annotation IDs or dropped predictions')
    rows = matrix['rows']
    if len(rows) != 2 or any(len(row) != 2 for row in rows):
        raise ValueError('Expected a complete binary confusion matrix')
    if any(not isinstance(v, int) or v < 0 for row in rows for v in row):
        raise ValueError('Confusion counts must be nonnegative integers')
    positive, negative = labels.index(default), labels.index('1' if default == '0' else '0')
    tp, fn = rows[positive][positive], rows[positive][negative]
    fp, tn = rows[negative][positive], rows[negative][negative]
    for key, value in [('truePositiveCount', tp), ('falseNegativeCount', fn),
                       ('falsePositiveCount', fp), ('trueNegativeCount', tn)]:
        if int(point.get(key, 0)) != value:
            raise ValueError('Class counts disagree with display-label confusion matrix')
    total = tp + fn + fp + tn
    expected = manifest['partitions']['TEST']
    if total != expected['rows'] or tp + fn != expected['defaults']:
        raise ValueError('Native evaluation has different holdout rows or default counts')
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0
    for key, value in [('precision', precision), ('recall', recall), ('f1Score', f1)]:
        if not math.isclose(float(point.get(key, 0)), value, abs_tol=1e-6):
            raise ValueError('Native class metric disagrees with confusion counts')
    roc, pr = (float(selected['metrics'][key]) for key in ['auRoc', 'auPrc'])
    if not all(math.isfinite(v) and 0 <= v <= 1 for v in [roc, pr]):
        raise ValueError('Invalid native ranking metrics')
    return {
        'origin': 'vertex-automl', 'model': model['displayName'],
        'dataset_sha256': manifest['dataset_sha256'], 'holdout_sha256': manifest['holdout_sha256'],
        'threshold': 0.5,
        'threshold_policy': 'Fixed default-class confidence 0.5 from native evaluation; no TEST tuning',
        'metrics': {'accuracy': (tp + tn) / total, 'default_precision': precision,
                    'default_recall': recall, 'default_f1': f1, 'roc_auc': roc,
                    'average_precision': None, 'native_auprc': pr,
                    'rows': total, 'default_prevalence': (tp + fn) / total,
                    'confusion_matrix': [[tp, fn], [fp, tn]]},
        'overall_native_metrics': {k: evaluation['metrics'].get(k) for k in ['auRoc', 'auPrc', 'logLoss']},
        'stability': {'temporal_f1_std': None, 'seed_f1_std': None,
                      'note': 'One AutoML run; retraining variance unmeasured. Native aggregates do not '
                              'supply individual predictions for bootstrap or chronological block analysis.'},
        'provenance': {'pipeline': pipeline['name'], 'model': model_name,
                       'version': model.get('versionId'), 'evaluation': evaluation['name'],
                       'default_slice': selected['name'], 'dataset': dataset['name'], 'input_uri': input_uri,
                       'manual_split_verified': True, 'test_class_counts_verified': True,
                       'prediction_features_verified': True,
                       'fingerprint_basis': 'Local uploaded-export manifest linked to native dataset URI, '
                                            'successful training pipeline and matching TEST class counts',
                       'paid_predictions_submitted': False},
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['evaluation', 'slices', 'pipeline', 'dataset', 'model', 'manifest']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--input-uri', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = normalize(**{name: json.loads(getattr(args, name).read_text())
                          for name in ['evaluation', 'slices', 'pipeline', 'dataset', 'model', 'manifest']},
                       input_uri=args.input_uri)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(report['metrics'], indent=2))

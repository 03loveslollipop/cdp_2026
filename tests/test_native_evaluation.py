"""Native aggregates must not become fabricated AP or majority-class metrics."""
import copy

import pytest

from cloud.native_evaluation import normalize


def native_fixture():
    model = {'name': 'projects/p/locations/r/models/m', 'displayName': 'demo',
             'versionId': '1', 'trainingPipeline': 'projects/p/locations/r/trainingPipelines/t'}
    evaluation = {'name': model['name'] + '@1/evaluations/e',
                  'metrics': {'auRoc': 0.99, 'auPrc': 0.98, 'logLoss': 0.2}}
    point = {'confidenceThreshold': 0.5, 'truePositiveCount': '5', 'falsePositiveCount': '2',
             'falseNegativeCount': '3', 'trueNegativeCount': '30',
             'precision': 5 / 7, 'recall': 5 / 8, 'f1Score': 2 / 3,
             'confusionMatrix': {'annotationSpecs': [{'id': '0', 'displayName': '1'},
                                                    {'id': '1', 'displayName': '0'}],
                                 'rows': [[30, 2], [3, 5]]}}
    slices = {'modelEvaluationSlices': [{'name': model['name'] + '/evaluations/e/slices/s',
               'slice': {'dimension': 'annotationSpec', 'value': '0'},
               'metrics': {'auRoc': 0.7, 'auPrc': 0.4, 'confidenceMetrics': [point]}}]}
    pipeline = {'name': model['trainingPipeline'], 'state': 'PIPELINE_STATE_SUCCEEDED',
                'inputDataConfig': {'datasetId': 'd', 'predefinedSplit': {'key': 'data_split'}},
                'trainingTaskInputs': {'targetColumn': 'Pago_atiempo',
                                       'transformations': [{'numeric': {'columnName': 'a'}}]}}
    dataset = {'name': 'projects/p/locations/r/datasets/d',
               'metadata': {'inputConfig': {'gcsSource': {'uri': ['gs://lab/automl.csv']}}}}
    manifest = {'split_column': 'data_split', 'target': 'Pago_atiempo', 'prediction_features': ['a'],
                'default_label': '0', 'dataset_sha256': 'data', 'holdout_sha256': 'test',
                'partitions': {'TEST': {'rows': 40, 'defaults': 8}}}
    return dict(evaluation=evaluation, slices=slices, pipeline=pipeline, dataset=dataset,
                model=model, manifest=manifest, input_uri='gs://lab/automl.csv')


def test_native_default_metrics_use_display_labels_and_keep_pr_definitions_separate():
    report = normalize(**native_fixture())
    assert report['metrics']['confusion_matrix'] == [[5, 3], [2, 30]]
    assert report['metrics']['accuracy'] == 35 / 40
    assert report['metrics']['default_f1'] == 2 / 3
    assert report['metrics']['roc_auc'] == 0.7
    assert report['overall_native_metrics']['auRoc'] == 0.99
    assert report['metrics']['average_precision'] is None
    assert report['metrics']['native_auprc'] == 0.4
    assert report['stability']['seed_f1_std'] is None


@pytest.mark.parametrize('mutation', ['different_holdout', 'no_exact_threshold', 'different_model',
                                     'different_version'])
def test_native_refuses_mismatched_provenance_or_threshold(mutation):
    data = copy.deepcopy(native_fixture())
    if mutation == 'different_holdout':
        data['manifest']['partitions']['TEST']['rows'] = 41
    elif mutation == 'no_exact_threshold':
        data['slices']['modelEvaluationSlices'][0]['metrics']['confidenceMetrics'][0]['confidenceThreshold'] = .495
    elif mutation == 'different_version':
        data['model']['versionId'] = '2'
    else:
        data['evaluation']['name'] = 'projects/p/locations/r/models/other/evaluations/e'
    with pytest.raises(ValueError):
        normalize(**data)

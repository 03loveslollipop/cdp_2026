"""Fail-closed quality gates and fair cloud-comparison contracts."""
import csv
import json
import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ci.check_metrics import check
from cloud.compare import compare, score_automl


def gate_fixture(tmp_path, **overrides):
    (tmp_path / 'selection.json').write_text(json.dumps({'model': 'random_forest'}))
    row = dict(model='random_forest', mean_f1=0.2, mean_roc_auc=0.65,
               temporal_f1_std=0.02, seed_f1_std=0.01)
    row.update(overrides)
    with (tmp_path / 'validation_summary.csv').open('w') as handle:
        writer = csv.DictWriter(handle, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
    return tmp_path


def test_quality_gate_rejects_low_auc_and_nonfinite_metrics(tmp_path):
    run = gate_fixture(tmp_path, mean_roc_auc=0.49)
    with pytest.raises(ValueError, match='gate failed'):
        check(run)
    assert not json.loads((run / 'quality-gate.json').read_text())['passed']
    gate_fixture(tmp_path, mean_f1=float('nan'))
    with pytest.raises(ValueError, match='Invalid mean_f1'):
        check(run)


def test_quality_gate_does_not_consult_holdout(tmp_path):
    run = gate_fixture(tmp_path)
    (run / 'holdout_summary.csv').write_text('deliberately not a metric table')
    assert check(run)['passed']


def test_completion_receipt_without_configured_jenkins_url(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'ci/notify.py'
    token = tmp_path / 'token'
    token.write_text('test-token')
    monkeypatch.chdir(tmp_path)
    for name in ('BUILD_URL', 'JENKINS_URL'):
        monkeypatch.delenv(name, raising=False)
    for name, value in {'JOB_NAME': 'folder/credit', 'BUILD_NUMBER': '5',
                        'PIPELINE_RESULT': 'SUCCESS', 'NOTIFY_URL': 'http://local/notify',
                        'NOTIFY_TOKEN_FILE': str(token)}.items():
        monkeypatch.setenv(name, value)
    response = MagicMock()
    response.__enter__.return_value.status = 202
    with patch('urllib.request.urlopen', return_value=response):
        runpy.run_path(str(script), run_name='__main__')
    receipt = json.loads((tmp_path / 'reports/notification.json').read_text())
    assert receipt['url'] == '/job/folder/job/credit/5/'
    assert receipt['status'] == 'SUCCESS'
    assert 'test-token' not in json.dumps(receipt)


def test_comparison_rejects_different_holdouts(tmp_path):
    paths = []
    for index in range(2):
        path = tmp_path / f'{index}.json'
        path.write_text(json.dumps({'dataset_sha256': 'same', 'holdout_sha256': str(index)}))
        paths.append(path)
    with pytest.raises(ValueError, match='different datasets or holdout'):
        compare(paths, tmp_path / 'report')


def test_automl_maps_class_zero_and_joins_reordered_keys(tmp_path):
    (tmp_path / 'manifest.json').write_text(json.dumps({'dataset_sha256': 'raw', 'holdout_sha256': 'test'}))
    (tmp_path / 'holdout-labels.csv').write_text('row_id,target\na,0\nb,0\nc,1\nd,1\n')
    path = tmp_path / 'predictions.jsonl'
    records = []
    for key, probability in [('d', 0.1), ('b', 0.9), ('a', 0.8), ('c', 0.2)]:
        records.append({'instance': {'row_id': key},
                        'prediction': {'classes': ['1', '0'], 'scores': [1-probability, probability]}})
    path.write_text('\n'.join(json.dumps(record) for record in records))
    output = tmp_path / 'result.json'
    report = score_automl([path], tmp_path, output)
    assert report['metrics']['default_f1'] == 1
    assert report['metrics']['roc_auc'] == 1
    path.write_text(path.read_text() + '\n' + json.dumps(records[0]))
    with pytest.raises(ValueError, match='duplicate prediction'):
        score_automl([path], tmp_path, output)

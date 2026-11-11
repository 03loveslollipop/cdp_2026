"""Training body used by the Vertex AI package uploaded through the dashboard."""
import json
from pathlib import Path
import tempfile

from mlops_pipeline.src.ft_engineering import chronological_train_test_split, read_raw_data
from mlops_pipeline.src.model_training_evaluation import load_training_config, train_and_evaluate

from cloud.prepare_data import frame_hash


def run(input_uri, expected_dataset_sha256, expected_holdout_sha256, output_dir):
    from google.cloud import storage

    if not input_uri.startswith('gs://'):
        raise ValueError('The dashboard pipeline requires a Cloud Storage raw CSV URI')
    bucket, name = input_uri[5:].split('/', 1)
    with tempfile.TemporaryDirectory(prefix='credit-vertex-') as temporary:
        source = Path(temporary) / 'raw.csv'
        storage.Client().bucket(bucket).blob(name).download_to_filename(source)
        raw = read_raw_data(input_path=source).reset_index(drop=True)
        if frame_hash(raw) != expected_dataset_sha256:
            raise ValueError('Input dataset fingerprint differs from the local benchmark')
        split = chronological_train_test_split(raw)
        if frame_hash(split.test) != expected_holdout_sha256:
            raise ValueError('Holdout fingerprint differs from the approved manifest')
        result = train_and_evaluate(raw, output_dir=output_dir,
                                    training_config=load_training_config('/app/ci/training.json'))
    return write_result(result, raw, output_dir, 'vertex-custom')


def write_result(result, raw, output_dir, origin):
    output = Path(output_dir)
    selected = result.best_model.model_name
    metric_row = result.holdout.set_index('model').loc[selected].to_dict()
    validation = result.comparison.set_index('model').loc[selected].to_dict()
    report = {
        'origin': origin, 'model': selected,
        'dataset_sha256': frame_hash(raw),
        'holdout_sha256': frame_hash(chronological_train_test_split(raw).test),
        'metrics': metric_row,
        'stability': {k: validation[k] for k in ['mean_f1', 'temporal_f1_std', 'seed_f1_std']},
        'threshold_policy': 'Temporal out-of-fold calibration and default-F1 threshold; frozen before holdout',
    }
    (output / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    return report

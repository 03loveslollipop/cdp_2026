"""SageMaker Processing entry point for the existing temporal credit benchmark."""
import json
import time
from pathlib import Path
from cloud.prepare_data import frame_hash
from cloud.training import write_result
from mlops_pipeline.src.ft_engineering import read_raw_data, chronological_train_test_split
from mlops_pipeline.src.model_training_evaluation import load_training_config, train_and_evaluate

started = time.monotonic()
raw = read_raw_data(input_path=Path('/opt/ml/processing/input/raw.csv')).reset_index(drop=True)
expected = '48e34610b823055a5f4e7a107142e25b08ba40920848eab1a68ff6396eb26927'
holdout = 'f0f8ec775541328cfcaf07fa5a8455a089b2f3832549c583de35804f5216329a'
if frame_hash(raw) != expected or frame_hash(chronological_train_test_split(raw).test) != holdout:
    raise ValueError('Dataset or chronological holdout fingerprint mismatch')
output = Path('/opt/ml/processing/output')
output.mkdir(parents=True, exist_ok=True)
result = train_and_evaluate(raw, output_dir=output, training_config=load_training_config('/app/ci/training.json'))
report = write_result(result, raw, output, 'aws-sagemaker-processing')
report['program_seconds'] = round(time.monotonic() - started, 2)
(output / 'comparison.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)

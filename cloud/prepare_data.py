"""Export leakage-safe AutoML tables and immutable comparison fingerprints locally."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from mlops_pipeline.src.ft_engineering import (
    build_data_preparation_pipeline, chronological_train_test_split,
    extract_dataset, load_config, read_raw_data,
)


def frame_hash(frame):
    return hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()


def prepare(destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    config = load_config()
    raw = read_raw_data().reset_index(drop=True)
    outer = chronological_train_test_split(raw, config)
    inner = chronological_train_test_split(outer.train, config, train_fraction=0.8)
    transform = build_data_preparation_pipeline(config)
    transform.fit(extract_dataset(inner.train, config, require_target=True).predictors)
    frames = []
    holdout = None
    counts = {}
    for name, frame in [('TRAIN', inner.train), ('VALIDATION', inner.test), ('TEST', outer.test)]:
        dataset = extract_dataset(frame, config, require_target=True)
        if set(dataset.target) != {0, 1}:
            raise ValueError(f'{name} must contain both classes')
        features = transform.transform(dataset.predictors).copy()
        features = features.reset_index(drop=True)
        for column in features.select_dtypes(include=['object', 'string', 'category']):
            features[column] = features[column].astype('string').fillna('Missing')
        forbidden = {config['schema']['target'], *config['leakage_columns'],
                     *config['predictive_pipeline']['metadata_columns']}
        if forbidden.intersection(features.columns):
            raise ValueError('Outcome or split metadata leaked into exported features')
        if features.isna().any().any():
            raise ValueError('Shared preparation left missing values')
        if name == 'TEST':
            holdout = features.copy()
            # The row key is never a training feature. Use it to join batch predictions.
            holdout.insert(0, 'row_id', frame.index.astype(str))
            labels = pd.DataFrame({'row_id': frame.index.astype(str), 'target': dataset.target.to_numpy()})
            labels.to_csv(destination / 'holdout-labels.csv', index=False)
        features['Pago_atiempo'] = dataset.target.to_numpy()
        features['data_split'] = name
        counts[name] = {'rows': len(frame), 'defaults': int((dataset.target == 0).sum())}
        frames.append(features)
    pd.concat(frames, ignore_index=True).to_csv(destination / 'automl.csv', index=False)
    holdout.to_csv(destination / 'holdout-features.csv', index=False)
    raw.to_csv(destination / 'raw.csv', sep=';', index=False)
    manifest = {
        'source_file_sha256': hashlib.sha256(Path('database.csv').read_bytes()).hexdigest(),
        'dataset_sha256': frame_hash(raw), 'holdout_sha256': frame_hash(outer.test),
        'raw_upload_sha256': hashlib.sha256((destination / 'raw.csv').read_bytes()).hexdigest(),
        'split': outer.summary, 'inner_split': inner.summary, 'partitions': counts,
        'target': 'Pago_atiempo', 'default_label': '0', 'split_column': 'data_split',
        'automl_preparation_fit': 'TRAIN partition only; approx. 56% of full dataset',
        'prediction_features': list(holdout.columns[1:]),
    }
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output)

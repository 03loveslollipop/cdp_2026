"""Compile a KFP v2 JSON package offline; launch it only in the GCP dashboard."""
import argparse
from pathlib import Path

from kfp import compiler, dsl


def compile_pipeline(image, output):
    if '@sha256:' not in image:
        raise ValueError('Use the published training image digest for reproducibility')

    @dsl.component(base_image=image, install_kfp_package=False)
    def train_credit(input_uri: str, dataset_sha256: str, holdout_sha256: str,
                     results: dsl.Output[dsl.Artifact], metrics: dsl.Output[dsl.Metrics]):
        from cloud.training import run
        report = run(input_uri, dataset_sha256, holdout_sha256, results.path)
        for name in ['accuracy', 'default_f1', 'roc_auc', 'average_precision']:
            metrics.log_metric(name, report['metrics'][name])
        for name, value in report['stability'].items():
            metrics.log_metric(name, value)

    @dsl.pipeline(name='credit-classification-temporal-comparison',
                  description='Same raw extract, temporal holdout and CPU protocol as the Python baseline')
    def credit_pipeline(input_uri: str, dataset_sha256: str, holdout_sha256: str):
        task = train_credit(input_uri=input_uri, dataset_sha256=dataset_sha256,
                            holdout_sha256=holdout_sha256)
        task.set_cpu_limit('2').set_memory_limit('8G').set_caching_options(False)

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(pipeline_func=credit_pipeline, package_path=str(output))
    print(f'Compiled dashboard-upload package: {output}. No GCP job was submitted.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, default=Path('cloud/pipeline.json'))
    args = parser.parse_args()
    compile_pipeline(args.image, args.output)

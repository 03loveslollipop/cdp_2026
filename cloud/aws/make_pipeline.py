"""Generate the SageMaker Pipelines definition; no resources or jobs are created."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--bucket', required=True)
parser.add_argument('--image', required=True, help='Immutable ECR image URI with @sha256 digest')
parser.add_argument('--role', required=True)
parser.add_argument('--output', type=Path, required=True)
a = parser.parse_args()
if '@sha256:' not in a.image:
    parser.error('An immutable ECR digest is required')
prefix = f's3://{a.bucket}'
execution_output = {'Std:Join': {'On': '/', 'Values': [prefix + '/runs', {'Get': 'Execution.PipelineExecutionId'}, 'results']}}
definition = {
    'Version': '2020-12-01',
    'Metadata': {},
    'Parameters': [],
    'Steps': [{
        'Name': 'TrainAndEvaluateTemporalCredit', 'Type': 'Processing',
        'Arguments': {
            'RoleArn': a.role,
            'AppSpecification': {'ImageUri': a.image},
            'ProcessingResources': {'ClusterConfig': {'InstanceCount': 1, 'InstanceType': 'ml.m5.large', 'VolumeSizeInGB': 10}},
            'StoppingCondition': {'MaxRuntimeInSeconds': 600},
            'ProcessingInputs': [{'InputName': 'raw', 'S3Input': {
                'S3Uri': prefix + '/input/raw.csv', 'LocalPath': '/opt/ml/processing/input',
                'S3DataType': 'S3Prefix', 'S3InputMode': 'File', 'S3DataDistributionType': 'FullyReplicated'}}],
            'ProcessingOutputConfig': {'Outputs': [{'OutputName': 'results', 'S3Output': {
                'S3Uri': execution_output, 'LocalPath': '/opt/ml/processing/output', 'S3UploadMode': 'EndOfJob'}}]},
        },
        'CacheConfig': {'Enabled': False}
    }]
}
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(definition, indent=2) + '\n')

# AWS credit comparison

This directory contains the isolated CloudFormation resources and SageMaker Processing entry point. It reuses the exact locally built `credit-semester-trainer:local` GCP image and the original temporal validation and holdout protocol. One Processing step runs on one CPU `ml.m5.large` with a 600-second maximum. It is a custom workflow; it is not SageMaker Autopilot. There is no endpoint or GPU.

CloudFormation creates an encrypted private S3 bucket (objects expire after seven days) and an ECR repository (images expire after seven days). The SageMaker pipeline uses the existing Learner Lab `LabRole`; it is a broad lab role, not a production least-privilege example. Pipeline JSON and execution receipts are saved under `output/aws-credit/`.

Delete only this demonstration after saving its results: delete the SageMaker pipeline, empty the specific stack bucket, delete its ECR image, and delete stack `credit-comparison-lab`. Lifecycle expiry removes objects/images but does not delete the bucket, repository or pipeline. The shared SageMaker Processing log group has a seven-day retention; the lab policy denied an attempt to restore indefinite retention, so this applies to later processing jobs too.

## Reproduction

From the repository root, build the shared base with `docker build -f cloud/Dockerfile -t credit-semester-trainer:local .` and then `docker build -f cloud/aws/Dockerfile -t credit-aws-comparison:local .`. Deploy the CloudFormation template with `aws cloudformation deploy --stack-name credit-comparison-lab --template-file cloud/aws/infrastructure.yaml`, upload the existing `output/cloud-data-gcp/raw.csv` to the stack bucket at `input/raw.csv`, and push the image to its ECR repository. Generate the pipeline definition with `make_pipeline.py --bucket BUCKET --image REPOSITORY@sha256:DIGEST --role ROLE_ARN --output pipeline.json`, then create it with `aws sagemaker create-pipeline` and start an execution. Starting an execution incurs usage charges. The recorded example definition is `output/aws-credit/pipeline.json`.

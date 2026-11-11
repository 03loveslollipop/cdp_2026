FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY cloud/requirements.txt /app/cloud/requirements.txt
RUN pip install --no-cache-dir -r cloud/requirements.txt
COPY mlops_pipeline/ /app/mlops_pipeline/
COPY config.json /app/config.json
COPY ci/training.json /app/ci/training.json
COPY cloud/*.py /app/cloud/
ENV MPLBACKEND=Agg PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 PYTHONPATH=/app
RUN useradd --uid 10001 --create-home trainer
USER trainer

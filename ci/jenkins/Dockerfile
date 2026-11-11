FROM jenkins/jenkins:lts-jdk21@sha256:74401de6a6f92e1afe1b02d1c8e3d0c33f263bfb5275dd8813f9150355f2367b
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/ci
ENV PATH="/opt/ci/bin:${PATH}"
COPY requirements-ci.txt /tmp/ci/requirements-ci.txt
COPY mlops_pipeline/src/deployment/requirements-serving.txt /tmp/ci/mlops_pipeline/src/deployment/requirements-serving.txt
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch>=2.2,<3' \
    && pip install --no-cache-dir -r /tmp/ci/requirements-ci.txt
COPY --chown=jenkins:jenkins ci/jenkins/plugins-cache/ /usr/share/jenkins/ref/plugins/
COPY ci/jenkins/init.groovy.d/ /usr/share/jenkins/ref/init.groovy.d/
USER jenkins

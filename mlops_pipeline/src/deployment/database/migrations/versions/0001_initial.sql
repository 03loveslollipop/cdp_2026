CREATE TABLE cdp_2026.model_versions (
    id VARCHAR(36) NOT NULL,
    artifact_sha256 VARCHAR(64) NOT NULL,
    model_family VARCHAR(64) NOT NULL,
    hyperparameters JSONB NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    class_order JSONB NOT NULL,
    training_fingerprint VARCHAR(64) NOT NULL,
    stage VARCHAR(32) NOT NULL,
    source_revision VARCHAR(64),
    manifest JSONB NOT NULL,
    active BOOLEAN NOT NULL,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT pk_model_versions PRIMARY KEY (id),
    CONSTRAINT uq_model_versions_artifact_sha256 UNIQUE (artifact_sha256)
);

-- migrate:split
CREATE TABLE cdp_2026.sample_loans (
    source_row_hash VARCHAR(64) NOT NULL,
    predictors JSONB NOT NULL,
    target INTEGER,
    loan_timestamp TIMESTAMPTZ,
    imported_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT pk_sample_loans PRIMARY KEY (source_row_hash),
    CONSTRAINT ck_sample_loans_target_binary
        CHECK (target IS NULL OR target IN (0, 1))
);

-- migrate:split
CREATE TABLE cdp_2026.prediction_batches (
    id VARCHAR(36) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    model_version_id VARCHAR(36) NOT NULL,
    status VARCHAR(24) NOT NULL,
    row_count INTEGER NOT NULL,
    duration_ms DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    completed_at TIMESTAMPTZ,
    CONSTRAINT pk_prediction_batches PRIMARY KEY (id),
    CONSTRAINT uq_prediction_batches_idempotency_key UNIQUE (idempotency_key),
    CONSTRAINT ck_prediction_batches_row_count_non_negative CHECK (row_count >= 0),
    CONSTRAINT fk_prediction_batches_model_version_id_model_versions
        FOREIGN KEY (model_version_id)
        REFERENCES cdp_2026.model_versions (id)
);

-- migrate:split
CREATE INDEX ix_prediction_batches_model_version_id
    ON cdp_2026.prediction_batches (model_version_id);

-- migrate:split
CREATE INDEX ix_prediction_batches_created_at
    ON cdp_2026.prediction_batches (created_at);

-- migrate:split
CREATE TABLE cdp_2026.prediction_events (
    id VARCHAR(36) NOT NULL,
    batch_id VARCHAR(36) NOT NULL,
    model_version_id VARCHAR(36) NOT NULL,
    row_number INTEGER NOT NULL,
    external_reference VARCHAR(128),
    predictors JSONB NOT NULL,
    default_probability DOUBLE PRECISION NOT NULL,
    on_time_probability DOUBLE PRECISION NOT NULL,
    predicted_label INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT pk_prediction_events PRIMARY KEY (id),
    CONSTRAINT uq_prediction_events_batch_id UNIQUE (batch_id, row_number),
    CONSTRAINT ck_prediction_events_row_number_non_negative CHECK (row_number >= 0),
    CONSTRAINT ck_prediction_events_default_probability_range
        CHECK (default_probability >= 0 AND default_probability <= 1),
    CONSTRAINT ck_prediction_events_on_time_probability_range
        CHECK (on_time_probability >= 0 AND on_time_probability <= 1),
    CONSTRAINT ck_prediction_events_predicted_label_binary
        CHECK (predicted_label IN (0, 1)),
    CONSTRAINT fk_prediction_events_batch_id_prediction_batches
        FOREIGN KEY (batch_id)
        REFERENCES cdp_2026.prediction_batches (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_prediction_events_model_version_id_model_versions
        FOREIGN KEY (model_version_id)
        REFERENCES cdp_2026.model_versions (id)
);

-- migrate:split
CREATE INDEX ix_prediction_events_batch_id
    ON cdp_2026.prediction_events (batch_id);

-- migrate:split
CREATE INDEX ix_prediction_events_model_version_id
    ON cdp_2026.prediction_events (model_version_id);

-- migrate:split
CREATE INDEX ix_prediction_events_external_reference
    ON cdp_2026.prediction_events (external_reference);

-- migrate:split
CREATE INDEX ix_prediction_events_created_at
    ON cdp_2026.prediction_events (created_at);

-- migrate:split
CREATE TABLE cdp_2026.observed_outcomes (
    id VARCHAR(36) NOT NULL,
    prediction_event_id VARCHAR(36) NOT NULL,
    actual_label INTEGER NOT NULL,
    matured_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT pk_observed_outcomes PRIMARY KEY (id),
    CONSTRAINT uq_observed_outcomes_prediction_event_id UNIQUE (prediction_event_id),
    CONSTRAINT ck_observed_outcomes_actual_label_binary CHECK (actual_label IN (0, 1)),
    CONSTRAINT fk_observed_outcomes_prediction_event_id_prediction_events
        FOREIGN KEY (prediction_event_id)
        REFERENCES cdp_2026.prediction_events (id)
        ON DELETE CASCADE
);

-- migrate:split
CREATE TABLE cdp_2026.reference_profiles (
    id VARCHAR(36) NOT NULL,
    model_version_id VARCHAR(36) NOT NULL,
    feature_name VARCHAR(128) NOT NULL,
    feature_type VARCHAR(24) NOT NULL,
    profile JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT pk_reference_profiles PRIMARY KEY (id),
    CONSTRAINT uq_reference_profiles_model_version_id
        UNIQUE (model_version_id, feature_name),
    CONSTRAINT fk_reference_profiles_model_version_id_model_versions
        FOREIGN KEY (model_version_id)
        REFERENCES cdp_2026.model_versions (id)
);

-- migrate:split
CREATE INDEX ix_reference_profiles_model_version_id
    ON cdp_2026.reference_profiles (model_version_id);

-- migrate:split
CREATE TABLE cdp_2026.monitoring_runs (
    id VARCHAR(36) NOT NULL,
    model_version_id VARCHAR(36) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    status VARCHAR(24) NOT NULL,
    started_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT pk_monitoring_runs PRIMARY KEY (id),
    CONSTRAINT uq_monitoring_runs_model_version_id
        UNIQUE (model_version_id, window_start, window_end),
    CONSTRAINT fk_monitoring_runs_model_version_id_model_versions
        FOREIGN KEY (model_version_id)
        REFERENCES cdp_2026.model_versions (id)
);

-- migrate:split
CREATE INDEX ix_monitoring_runs_model_version_id
    ON cdp_2026.monitoring_runs (model_version_id);

-- migrate:split
CREATE TABLE cdp_2026.monitoring_metrics (
    id VARCHAR(36) NOT NULL,
    run_id VARCHAR(36) NOT NULL,
    metric_name VARCHAR(128) NOT NULL,
    feature_name VARCHAR(128),
    feature_key VARCHAR(128) NOT NULL,
    metric_value DOUBLE PRECISION,
    status VARCHAR(24) NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT pk_monitoring_metrics PRIMARY KEY (id),
    CONSTRAINT uq_monitoring_metrics_run_id
        UNIQUE (run_id, metric_name, feature_key),
    CONSTRAINT fk_monitoring_metrics_run_id_monitoring_runs
        FOREIGN KEY (run_id)
        REFERENCES cdp_2026.monitoring_runs (id)
);

-- migrate:split
CREATE INDEX ix_monitoring_metrics_run_id
    ON cdp_2026.monitoring_metrics (run_id);

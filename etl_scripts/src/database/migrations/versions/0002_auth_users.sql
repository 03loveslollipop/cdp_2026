CREATE TABLE cdp_2026.auth_users (
    id VARCHAR(36) NOT NULL,
    username VARCHAR(128) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(16) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    token_version INTEGER NOT NULL DEFAULT 0,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_auth_users PRIMARY KEY (id),
    CONSTRAINT uq_auth_users_username UNIQUE (username),
    CONSTRAINT ck_auth_users_role_valid
        CHECK (role IN ('inference', 'owner')),
    CONSTRAINT ck_auth_users_token_version_non_negative
        CHECK (token_version >= 0),
    CONSTRAINT ck_auth_users_password_hash_argon2id
        CHECK (password_hash LIKE '$argon2id$%')
);

-- migrate:split
CREATE INDEX ix_auth_users_username
    ON cdp_2026.auth_users (username);

-- migrate:split
ALTER TABLE cdp_2026.prediction_batches
    ADD COLUMN requested_by_user_id VARCHAR(36);

-- migrate:split
ALTER TABLE cdp_2026.prediction_batches
    ADD CONSTRAINT fk_prediction_batches_requested_by_user_id_auth_users
    FOREIGN KEY (requested_by_user_id)
    REFERENCES cdp_2026.auth_users (id)
    ON DELETE SET NULL;

-- migrate:split
ALTER TABLE cdp_2026.prediction_batches
    DROP CONSTRAINT uq_prediction_batches_idempotency_key;

-- migrate:split
ALTER TABLE cdp_2026.prediction_batches
    ADD CONSTRAINT uq_prediction_batches_user_idempotency_key
    UNIQUE NULLS NOT DISTINCT (requested_by_user_id, idempotency_key);

-- migrate:split
CREATE INDEX ix_prediction_batches_requested_by_user_id
    ON cdp_2026.prediction_batches (requested_by_user_id);

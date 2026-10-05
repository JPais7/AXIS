-- Phase 3.9 additive chemical-learning layer. 001-012 unchanged.
-- Datasets, models and predictions are immutable; observed SAR, SAR hypotheses,
-- model predictions and experimental measurements are different objects.
CREATE TABLE chemical_learning_datasets (
    id VARCHAR PRIMARY KEY,
    logical_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    project_id VARCHAR NOT NULL,
    checksum VARCHAR NOT NULL,
    synthetic BOOLEAN NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (logical_id, revision)
);
CREATE TABLE measurement_comparability_assessments (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    dataset_a VARCHAR NOT NULL REFERENCES chemical_learning_datasets(id),
    dataset_b VARCHAR NOT NULL REFERENCES chemical_learning_datasets(id),
    state VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE observed_sar (
    id VARCHAR PRIMARY KEY,
    dataset_id VARCHAR NOT NULL REFERENCES chemical_learning_datasets(id),
    project_id VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE sar_hypotheses (
    id VARCHAR PRIMARY KEY,
    dataset_id VARCHAR NOT NULL REFERENCES chemical_learning_datasets(id),
    project_id VARCHAR NOT NULL,
    epistemic_status VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE model_eligibility_assessments (
    id VARCHAR PRIMARY KEY,
    dataset_id VARCHAR NOT NULL REFERENCES chemical_learning_datasets(id),
    project_id VARCHAR NOT NULL,
    conclusion VARCHAR NOT NULL,
    readiness VARCHAR NOT NULL,
    policy_fingerprint VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE chemical_models (
    id VARCHAR PRIMARY KEY,
    dataset_id VARCHAR NOT NULL REFERENCES chemical_learning_datasets(id),
    project_id VARCHAR NOT NULL,
    algorithm VARCHAR NOT NULL,
    fingerprint VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE chemical_predictions (
    id VARCHAR PRIMARY KEY,
    model_id VARCHAR NOT NULL REFERENCES chemical_models(id),
    project_id VARCHAR NOT NULL,
    compound_ref VARCHAR NOT NULL,
    intent VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE prediction_outcome_assessments (
    id VARCHAR PRIMARY KEY,
    prediction_id VARCHAR NOT NULL REFERENCES chemical_predictions(id),
    project_id VARCHAR NOT NULL,
    conclusion VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE chemical_learning_states (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    logical_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (logical_id, revision)
);
CREATE TABLE chemical_learning_reviews (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    object_type VARCHAR NOT NULL,
    object_id VARCHAR NOT NULL,
    reviewer VARCHAR NOT NULL,
    decision VARCHAR NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);

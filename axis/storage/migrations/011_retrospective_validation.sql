-- Phase 3.7 additive retrospective-validation layer. 001-010 unchanged.
-- Benchmarks never write to discovery projects, claims or decision states: a
-- retrospective decision is a validation artefact, not project knowledge.
CREATE TABLE benchmark_sets (
    set_id VARCHAR PRIMARY KEY,
    manifest_sha256 VARCHAR NOT NULL,
    benchmark_kind VARCHAR NOT NULL,
    synthetic BOOLEAN NOT NULL,
    title VARCHAR NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE benchmark_cases (
    case_id VARCHAR PRIMARY KEY,
    set_id VARCHAR NOT NULL REFERENCES benchmark_sets(set_id),
    status VARCHAR NOT NULL,
    protocol_fingerprint VARCHAR NOT NULL,
    payload JSON NOT NULL,
    sealed_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE temporal_snapshots (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL REFERENCES benchmark_cases(case_id),
    cutoff DATE NOT NULL,
    fingerprint VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (case_id, fingerprint)
);
CREATE TABLE benchmark_runs (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL REFERENCES benchmark_cases(case_id),
    phase VARCHAR NOT NULL,
    rules_fingerprint VARCHAR NOT NULL,
    software_commit VARCHAR NOT NULL,
    review_mode VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE leakage_audits (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL REFERENCES benchmark_cases(case_id),
    phase VARCHAR NOT NULL,
    valid BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE retrospective_assessments (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL REFERENCES benchmark_cases(case_id),
    run_id VARCHAR NOT NULL REFERENCES benchmark_runs(id),
    conclusion VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE benchmark_baselines (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL REFERENCES benchmark_cases(case_id),
    baseline_kind VARCHAR NOT NULL,
    run_label VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    frozen_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (case_id, baseline_kind, run_label)
);
CREATE TABLE benchmark_blind_packets (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL REFERENCES benchmark_cases(case_id),
    mapping_sha256 VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    unblinded_at TIMESTAMPTZ,
    packet JSON NOT NULL,
    sealed_mapping JSON NOT NULL
);
CREATE TABLE benchmark_reviews (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL REFERENCES benchmark_cases(case_id),
    reviewer VARCHAR NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE benchmark_rule_notes (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR REFERENCES benchmark_cases(case_id),
    kind VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);

-- Phase 3.8 additive computational-discovery layer. 001-011 unchanged.
-- Computational observations are never experimental results; campaigns, prepared
-- structures/compounds and prioritizations are immutable once written.
CREATE TABLE chemical_hypotheses (
    id VARCHAR PRIMARY KEY,
    logical_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    project_id VARCHAR NOT NULL,
    epistemic_status VARCHAR NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (logical_id, revision)
);
CREATE TABLE prepared_structures (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    source_structure_id VARCHAR NOT NULL,
    source_sha256 VARCHAR NOT NULL,
    output_sha256 VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE prepared_compounds (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    compound_ref VARCHAR NOT NULL,
    output_sha256 VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE chemical_spaces (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    checksum VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE chemical_space_members (
    space_id VARCHAR NOT NULL REFERENCES chemical_spaces(id),
    compound_ref VARCHAR NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (space_id, compound_ref)
);
CREATE TABLE computational_campaigns (
    id VARCHAR PRIMARY KEY,
    logical_id VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    project_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (logical_id, revision)
);
CREATE TABLE computational_observations (
    id VARCHAR PRIMARY KEY,
    campaign_id VARCHAR NOT NULL REFERENCES computational_campaigns(id),
    compound_ref VARCHAR NOT NULL,
    method VARCHAR NOT NULL,
    epistemic_class VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE candidate_molecules (
    id VARCHAR PRIMARY KEY,
    campaign_id VARCHAR NOT NULL REFERENCES computational_campaigns(id),
    compound_ref VARCHAR NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (campaign_id, compound_ref)
);
CREATE TABLE candidate_prioritizations (
    id VARCHAR PRIMARY KEY,
    campaign_id VARCHAR NOT NULL REFERENCES computational_campaigns(id),
    rules_fingerprint VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE campaign_artifacts (
    id VARCHAR PRIMARY KEY,
    campaign_id VARCHAR NOT NULL REFERENCES computational_campaigns(id),
    artifact_type VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE campaign_reviews (
    id VARCHAR PRIMARY KEY,
    campaign_id VARCHAR NOT NULL REFERENCES computational_campaigns(id),
    object_id VARCHAR NOT NULL,
    reviewer VARCHAR NOT NULL,
    decision VARCHAR NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL
);

-- Phase 3.6 additive experimental-results layer. 001-009 unchanged.
-- Proposal, performance, result, interpretation, review and decision stay separate.
CREATE TABLE experiment_artifacts (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    uri VARCHAR NOT NULL,
    sha256 VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    size_bytes BIGINT NOT NULL,
    role VARCHAR NOT NULL,
    description VARCHAR NOT NULL
);
CREATE TABLE performed_experiments (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    protein_id VARCHAR REFERENCES protein_identities(id),
    proposal_id VARCHAR REFERENCES proposed_experiments(experiment_id),
    scope_type VARCHAR NOT NULL,
    scope_id VARCHAR NOT NULL,
    scientific_status VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE experiment_design_deviations (
    id VARCHAR PRIMARY KEY,
    performed_experiment_id VARCHAR NOT NULL REFERENCES performed_experiments(id),
    proposal_id VARCHAR REFERENCES proposed_experiments(experiment_id),
    payload JSON NOT NULL
);
CREATE TABLE experimental_quality_assessments (
    id VARCHAR PRIMARY KEY,
    performed_experiment_id VARCHAR NOT NULL REFERENCES performed_experiments(id),
    supersedes_id VARCHAR REFERENCES experimental_quality_assessments(id),
    assessment VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE experimental_results (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    logical_id VARCHAR NOT NULL,
    version INTEGER NOT NULL,
    supersedes_id VARCHAR REFERENCES experimental_results(id),
    performed_experiment_id VARCHAR NOT NULL REFERENCES performed_experiments(id),
    endpoint VARCHAR NOT NULL,
    result_type VARCHAR NOT NULL,
    knowledge_kind VARCHAR NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (logical_id, version)
);
CREATE TABLE result_artifacts (
    result_id VARCHAR NOT NULL REFERENCES experimental_results(id),
    artifact_id VARCHAR NOT NULL REFERENCES experiment_artifacts(id),
    role VARCHAR NOT NULL,
    PRIMARY KEY (result_id, artifact_id, role)
);
CREATE TABLE result_events (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    result_id VARCHAR NOT NULL REFERENCES experimental_results(id),
    event_type VARCHAR NOT NULL,
    actor VARCHAR NOT NULL,
    note VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE result_interpretations (
    id VARCHAR PRIMARY KEY,
    result_id VARCHAR NOT NULL REFERENCES experimental_results(id),
    edge VARCHAR NOT NULL,
    scope_type VARCHAR NOT NULL,
    scope_id VARCHAR NOT NULL,
    knowledge_kind VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE scenario_signatures (
    scenario_id VARCHAR PRIMARY KEY REFERENCES outcome_scenarios(scenario_id),
    payload JSON NOT NULL
);
CREATE TABLE scenario_match_assessments (
    id VARCHAR PRIMARY KEY,
    result_id VARCHAR NOT NULL REFERENCES experimental_results(id),
    outcome_scenario_id VARCHAR REFERENCES outcome_scenarios(scenario_id),
    relationship VARCHAR NOT NULL,
    rule_version VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE scientific_reviews (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    object_type VARCHAR NOT NULL,
    object_id VARCHAR NOT NULL,
    reviewer VARCHAR NOT NULL,
    decision VARCHAR NOT NULL,
    rationale VARCHAR NOT NULL,
    caveat VARCHAR,
    supersedes_review_id VARCHAR REFERENCES scientific_reviews(id),
    reviewed_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE decision_result_links (
    decision_state_id VARCHAR NOT NULL REFERENCES decision_states(id),
    result_id VARCHAR NOT NULL REFERENCES experimental_results(id),
    interpretation_id VARCHAR NOT NULL REFERENCES result_interpretations(id),
    eligibility VARCHAR NOT NULL,
    review_state VARCHAR NOT NULL,
    PRIMARY KEY (decision_state_id, result_id, interpretation_id)
);

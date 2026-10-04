-- Phase 3.5 additive experimental decision layer. Reuses hypotheses,
-- proposed_experiments, outcome_scenarios and open_questions; 001-008 unchanged.
CREATE TABLE decision_explanations (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    protein_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    hypothesis_id VARCHAR NOT NULL REFERENCES hypotheses(identifier),
    hypothesis_revision INTEGER NOT NULL,
    ground VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE decision_states (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    protein_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    version INTEGER NOT NULL,
    supersedes_id VARCHAR REFERENCES decision_states(id),
    hypothesis_id VARCHAR NOT NULL REFERENCES hypotheses(identifier),
    hypothesis_revision INTEGER NOT NULL,
    critical_uncertainty_id VARCHAR,
    recommended_experiment_id VARCHAR REFERENCES proposed_experiments(experiment_id),
    evidence_digest VARCHAR NOT NULL,
    rules_version VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSON NOT NULL,
    UNIQUE (project_id, protein_id, version)
);
CREATE TABLE decision_uncertainties (
    decision_state_id VARCHAR NOT NULL REFERENCES decision_states(id),
    id VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    decision_relevance VARCHAR NOT NULL,
    resolvability VARCHAR NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (decision_state_id, id)
);
CREATE TABLE decision_uncertainty_gaps (
    decision_state_id VARCHAR NOT NULL,
    uncertainty_id VARCHAR NOT NULL,
    gap_id VARCHAR NOT NULL REFERENCES open_questions(question_id),
    PRIMARY KEY (decision_state_id, uncertainty_id, gap_id),
    FOREIGN KEY (decision_state_id, uncertainty_id)
        REFERENCES decision_uncertainties(decision_state_id, id)
);
CREATE TABLE decision_explanation_states (
    decision_state_id VARCHAR NOT NULL REFERENCES decision_states(id),
    explanation_id VARCHAR NOT NULL REFERENCES decision_explanations(id),
    status VARCHAR NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (decision_state_id, explanation_id)
);
CREATE TABLE decision_explanation_links (
    decision_state_id VARCHAR NOT NULL,
    explanation_id VARCHAR NOT NULL,
    ordinal INTEGER NOT NULL,
    relationship VARCHAR NOT NULL,
    evidence_type VARCHAR NOT NULL,
    evidence_id VARCHAR NOT NULL,
    rule_id VARCHAR NOT NULL,
    rationale VARCHAR NOT NULL,
    PRIMARY KEY (decision_state_id, explanation_id, ordinal),
    FOREIGN KEY (decision_state_id, explanation_id)
        REFERENCES decision_explanation_states(decision_state_id, explanation_id)
);
CREATE TABLE critical_uncertainty_assessments (
    decision_state_id VARCHAR PRIMARY KEY REFERENCES decision_states(id),
    selected_uncertainty_id VARCHAR,
    payload JSON NOT NULL
);
CREATE TABLE candidate_experiment_profiles (
    experiment_id VARCHAR PRIMARY KEY REFERENCES proposed_experiments(experiment_id),
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    protein_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    purpose VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE decision_experiment_gaps (
    experiment_id VARCHAR NOT NULL REFERENCES candidate_experiment_profiles(experiment_id),
    gap_id VARCHAR NOT NULL REFERENCES open_questions(question_id),
    PRIMARY KEY (experiment_id, gap_id)
);
CREATE TABLE decision_experiment_discriminates (
    experiment_id VARCHAR NOT NULL REFERENCES candidate_experiment_profiles(experiment_id),
    explanation_id VARCHAR NOT NULL REFERENCES decision_explanations(id),
    PRIMARY KEY (experiment_id, explanation_id)
);
CREATE TABLE outcome_interpretations (
    scenario_id VARCHAR NOT NULL REFERENCES outcome_scenarios(scenario_id),
    explanation_id VARCHAR NOT NULL REFERENCES decision_explanations(id),
    effect VARCHAR NOT NULL,
    rationale VARCHAR NOT NULL,
    PRIMARY KEY (scenario_id, explanation_id)
);
CREATE TABLE decision_consequences (
    scenario_id VARCHAR PRIMARY KEY REFERENCES outcome_scenarios(scenario_id),
    scenario_kind VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE decision_constraints (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    version INTEGER NOT NULL,
    supersedes_id VARCHAR REFERENCES decision_constraints(id),
    payload JSON NOT NULL,
    UNIQUE (project_id, version)
);
CREATE TABLE decision_events (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    subject_type VARCHAR NOT NULL,
    subject_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    from_value VARCHAR NOT NULL,
    to_value VARCHAR NOT NULL,
    actor VARCHAR NOT NULL,
    note VARCHAR NOT NULL,
    result_claim_id VARCHAR REFERENCES claims(identifier),
    created_at TIMESTAMPTZ NOT NULL
);

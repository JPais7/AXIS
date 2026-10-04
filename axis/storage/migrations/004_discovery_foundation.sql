CREATE TABLE target_disease_pairs (
    pair_id VARCHAR PRIMARY KEY,
    identity_key VARCHAR NOT NULL UNIQUE,
    target_kind VARCHAR NOT NULL CHECK(target_kind IN ('gene', 'protein')),
    target_namespace VARCHAR NOT NULL,
    target_identifier VARCHAR NOT NULL,
    disease_kind VARCHAR NOT NULL CHECK(disease_kind = 'disease'),
    disease_namespace VARCHAR NOT NULL,
    disease_identifier VARCHAR NOT NULL,
    indication_scope VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY(target_kind, target_namespace, target_identifier)
        REFERENCES entities(kind, namespace, identifier),
    FOREIGN KEY(disease_kind, disease_namespace, disease_identifier)
        REFERENCES entities(kind, namespace, identifier)
);
CREATE TABLE discovery_projects (
    project_id VARCHAR PRIMARY KEY,
    target_disease_pair VARCHAR NOT NULL REFERENCES target_disease_pairs(pair_id),
    objective VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK(status IN ('draft', 'active', 'paused', 'archived')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL CHECK(updated_at >= created_at)
);
CREATE TABLE project_claims (
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    claim_id VARCHAR NOT NULL REFERENCES claims(identifier),
    PRIMARY KEY(project_id, claim_id)
);
CREATE TABLE discovery_perturbations (
    perturbation_id VARCHAR PRIMARY KEY,
    target_kind VARCHAR NOT NULL CHECK(target_kind IN ('gene', 'protein')),
    target_namespace VARCHAR NOT NULL,
    target_identifier VARCHAR NOT NULL,
    perturbation_type VARCHAR NOT NULL,
    direction VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK(status IN ('proposed', 'performed')),
    provenance JSON NOT NULL,
    knowledge_kind VARCHAR NOT NULL,
    scientific_context JSON NOT NULL,
    intervention_kind VARCHAR,
    intervention_namespace VARCHAR,
    intervention_identifier VARCHAR,
    observed_effect_claim_id VARCHAR REFERENCES claims(identifier),
    CHECK(status = 'performed' OR observed_effect_claim_id IS NULL),
    FOREIGN KEY(target_kind, target_namespace, target_identifier)
        REFERENCES entities(kind, namespace, identifier),
    FOREIGN KEY(intervention_kind, intervention_namespace, intervention_identifier)
        REFERENCES entities(kind, namespace, identifier)
);
CREATE TABLE project_perturbations (
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    perturbation_id VARCHAR NOT NULL REFERENCES discovery_perturbations(perturbation_id),
    PRIMARY KEY(project_id, perturbation_id)
);
CREATE TABLE intervention_strategies (
    strategy_id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    strategy_type VARCHAR NOT NULL,
    description VARCHAR NOT NULL,
    rationale VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    knowledge_kind VARCHAR NOT NULL,
    UNIQUE(project_id, strategy_id)
);
CREATE TABLE open_questions (
    question_id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    question VARCHAR NOT NULL,
    uncertainty_type VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL CHECK(updated_at >= created_at),
    scientific_context JSON NOT NULL,
    UNIQUE(project_id, question_id)
);
CREATE TABLE question_claims (
    question_id VARCHAR NOT NULL REFERENCES open_questions(question_id),
    claim_id VARCHAR NOT NULL REFERENCES claims(identifier),
    PRIMARY KEY(question_id, claim_id)
);
CREATE TABLE question_hypotheses (
    question_id VARCHAR NOT NULL REFERENCES open_questions(question_id),
    hypothesis_id VARCHAR NOT NULL REFERENCES hypotheses(identifier),
    PRIMARY KEY(question_id, hypothesis_id)
);
CREATE TABLE question_strategies (
    question_id VARCHAR NOT NULL REFERENCES open_questions(question_id),
    strategy_id VARCHAR NOT NULL REFERENCES intervention_strategies(strategy_id),
    PRIMARY KEY(question_id, strategy_id)
);
CREATE TABLE question_perturbations (
    question_id VARCHAR NOT NULL REFERENCES open_questions(question_id),
    perturbation_id VARCHAR NOT NULL REFERENCES discovery_perturbations(perturbation_id),
    PRIMARY KEY(question_id, perturbation_id)
);
CREATE TABLE evidence_assessments (
    assessment_id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    claim_id VARCHAR NOT NULL,
    role VARCHAR NOT NULL CHECK(role IN (
        'supports', 'weakly_supports', 'contradicts', 'neutral',
        'inconclusive', 'untyped_considered')),
    reasoning VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    strategy_id VARCHAR,
    question_id VARCHAR,
    hypothesis_id VARCHAR,
    hypothesis_revision INTEGER,
    FOREIGN KEY(project_id, claim_id) REFERENCES project_claims(project_id, claim_id),
    FOREIGN KEY(project_id, strategy_id)
        REFERENCES intervention_strategies(project_id, strategy_id),
    FOREIGN KEY(project_id, question_id) REFERENCES open_questions(project_id, question_id),
    FOREIGN KEY(hypothesis_id, hypothesis_revision)
        REFERENCES hypothesis_revisions(hypothesis_identifier, revision),
    CHECK ((CASE WHEN strategy_id IS NULL THEN 0 ELSE 1 END
          + CASE WHEN question_id IS NULL THEN 0 ELSE 1 END
          + CASE WHEN hypothesis_id IS NULL THEN 0 ELSE 1 END) = 1),
    CHECK ((hypothesis_id IS NULL AND hypothesis_revision IS NULL)
        OR (hypothesis_id IS NOT NULL AND hypothesis_revision >= 1))
);
CREATE TABLE mechanistic_assessments (
    assessment_id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL,
    claim_id VARCHAR NOT NULL,
    classification VARCHAR NOT NULL CHECK(classification IN (
        'directly_demonstrated', 'inferred', 'computationally_predicted', 'hypothesized')),
    reasoning VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    FOREIGN KEY(project_id, claim_id) REFERENCES project_claims(project_id, claim_id)
);
CREATE TABLE proposed_experiments (
    experiment_id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    question_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    rationale VARCHAR NOT NULL,
    experimental_system VARCHAR NOT NULL,
    intervention_description VARCHAR NOT NULL,
    endpoint_description VARCHAR NOT NULL,
    provenance JSON NOT NULL,
    suggestion_origin VARCHAR NOT NULL,
    knowledge_kind VARCHAR NOT NULL CHECK(knowledge_kind IN (
        'ai_suggestion', 'researcher_hypothesis', 'axis_inference')),
    status VARCHAR NOT NULL,
    scientific_context JSON NOT NULL,
    FOREIGN KEY(project_id, question_id) REFERENCES open_questions(project_id, question_id)
);
CREATE TABLE outcome_scenarios (
    scenario_id VARCHAR PRIMARY KEY,
    experiment_id VARCHAR NOT NULL REFERENCES proposed_experiments(experiment_id),
    possible_outcome VARCHAR NOT NULL,
    interpretation VARCHAR NOT NULL
);

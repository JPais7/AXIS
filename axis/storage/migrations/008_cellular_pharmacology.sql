CREATE TABLE cellular_experiments (
    id VARCHAR PRIMARY KEY,
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    protein_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    perturbation_id VARCHAR NOT NULL REFERENCES discovery_perturbations(perturbation_id),
    compound_id VARCHAR REFERENCES compound_identities(id),
    payload JSON NOT NULL
);
CREATE TABLE experimental_readouts (
    id VARCHAR PRIMARY KEY,
    experiment_id VARCHAR NOT NULL REFERENCES cellular_experiments(id),
    claim_id VARCHAR REFERENCES claims(identifier),
    measurement_id VARCHAR REFERENCES bioactivity_measurements(id),
    payload JSON NOT NULL
);
CREATE TABLE cellular_assessments (
    id VARCHAR PRIMARY KEY,
    experiment_id VARCHAR NOT NULL REFERENCES cellular_experiments(id),
    edge VARCHAR NOT NULL,
    payload JSON NOT NULL
);
CREATE TABLE immunopeptidome_observations (
    id VARCHAR PRIMARY KEY,
    readout_id VARCHAR NOT NULL REFERENCES experimental_readouts(id),
    payload JSON NOT NULL
);
CREATE TABLE cellular_gap_links (
    question_id VARCHAR PRIMARY KEY REFERENCES open_questions(question_id),
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    protein_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    compound_id VARCHAR REFERENCES compound_identities(id),
    perturbation_id VARCHAR NOT NULL REFERENCES discovery_perturbations(perturbation_id),
    edge VARCHAR NOT NULL,
    payload JSON NOT NULL
);

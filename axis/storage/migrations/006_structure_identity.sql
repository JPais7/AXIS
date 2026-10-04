CREATE TABLE protein_constructs (
    id VARCHAR PRIMARY KEY,
    protein_identity_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
    payload JSON NOT NULL
);
CREATE TABLE experimental_structures (
    id VARCHAR PRIMARY KEY,
    source_snapshot_id VARCHAR NOT NULL REFERENCES source_snapshots(id),
    payload JSON NOT NULL,
    coordinates BLOB NOT NULL
);
CREATE TABLE structure_chains (
    id VARCHAR PRIMARY KEY,
    structure_id VARCHAR NOT NULL REFERENCES experimental_structures(id),
    construct_id VARCHAR NOT NULL REFERENCES protein_constructs(id),
    payload JSON NOT NULL
);
CREATE TABLE residue_mappings (
    chain_id VARCHAR PRIMARY KEY REFERENCES structure_chains(id),
    payload JSON NOT NULL,
    transformation JSON NOT NULL
);
CREATE TABLE observed_structure_components (
    structure_id VARCHAR PRIMARY KEY REFERENCES experimental_structures(id),
    payload JSON NOT NULL
);
CREATE TABLE project_structures (
    project_id VARCHAR NOT NULL REFERENCES discovery_projects(project_id),
    protein_identity_id VARCHAR NOT NULL REFERENCES protein_identities(id),
    structure_id VARCHAR NOT NULL REFERENCES experimental_structures(id),
    PRIMARY KEY(project_id, protein_identity_id, structure_id)
);

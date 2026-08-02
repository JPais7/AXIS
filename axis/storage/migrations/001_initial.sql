CREATE TABLE entities (
    kind VARCHAR NOT NULL,
    namespace VARCHAR NOT NULL,
    identifier VARCHAR NOT NULL,
    label VARCHAR NOT NULL,
    PRIMARY KEY (kind, namespace, identifier)
);

CREATE TABLE claims (
    identifier VARCHAR PRIMARY KEY,
    subject_kind VARCHAR NOT NULL,
    subject_namespace VARCHAR NOT NULL,
    subject_identifier VARCHAR NOT NULL,
    predicate VARCHAR NOT NULL,
    object_kind VARCHAR NOT NULL,
    object_namespace VARCHAR NOT NULL,
    object_identifier VARCHAR NOT NULL,
    knowledge_kind VARCHAR NOT NULL,
    confidence DOUBLE,
    tissue VARCHAR,
    assay VARCHAR,
    population VARCHAR,
    comparison VARCHAR,
    treatment VARCHAR,
    species VARCHAR,
    source_kind VARCHAR NOT NULL,
    source_identifier VARCHAR NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    source_uri VARCHAR,
    checksum VARCHAR,
    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    FOREIGN KEY (subject_kind, subject_namespace, subject_identifier)
        REFERENCES entities (kind, namespace, identifier),
    FOREIGN KEY (object_kind, object_namespace, object_identifier)
        REFERENCES entities (kind, namespace, identifier)
);

CREATE TABLE claim_transformations (
    claim_identifier VARCHAR NOT NULL,
    ordinal INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    PRIMARY KEY (claim_identifier, ordinal),
    FOREIGN KEY (claim_identifier) REFERENCES claims (identifier)
);

CREATE TABLE transformation_parameters (
    claim_identifier VARCHAR NOT NULL,
    transformation_ordinal INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    key VARCHAR NOT NULL,
    value VARCHAR NOT NULL,
    PRIMARY KEY (claim_identifier, transformation_ordinal, ordinal),
    FOREIGN KEY (claim_identifier, transformation_ordinal)
        REFERENCES claim_transformations (claim_identifier, ordinal)
);

CREATE TABLE hypotheses (
    identifier VARCHAR PRIMARY KEY,
    title VARCHAR NOT NULL
);

CREATE TABLE hypothesis_revisions (
    hypothesis_identifier VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    state VARCHAR NOT NULL,
    description VARCHAR NOT NULL,
    rationale VARCHAR NOT NULL,
    confidence DOUBLE,
    PRIMARY KEY (hypothesis_identifier, revision),
    CHECK (revision >= 1),
    CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    FOREIGN KEY (hypothesis_identifier) REFERENCES hypotheses (identifier)
);

CREATE TABLE hypothesis_evidence (
    hypothesis_identifier VARCHAR NOT NULL,
    revision INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    claim_identifier VARCHAR NOT NULL,
    PRIMARY KEY (hypothesis_identifier, revision, ordinal),
    FOREIGN KEY (hypothesis_identifier, revision)
        REFERENCES hypothesis_revisions (hypothesis_identifier, revision),
    FOREIGN KEY (claim_identifier) REFERENCES claims (identifier)
);

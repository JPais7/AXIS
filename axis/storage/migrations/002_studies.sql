CREATE TABLE studies (
    identifier VARCHAR PRIMARY KEY,
    title VARCHAR NOT NULL,
    summary VARCHAR NOT NULL,
    source VARCHAR NOT NULL,
    experiment_type VARCHAR,
    sample_count INTEGER,
    bioproject_id VARCHAR,
    released_on DATE,
    provenance_source_kind VARCHAR NOT NULL,
    provenance_source_identifier VARCHAR NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    source_uri VARCHAR,
    checksum VARCHAR,
    CHECK (sample_count IS NULL OR sample_count >= 0)
);

CREATE TABLE study_organisms (
    study_identifier VARCHAR NOT NULL,
    ordinal INTEGER NOT NULL,
    organism VARCHAR NOT NULL,
    PRIMARY KEY (study_identifier, ordinal),
    FOREIGN KEY (study_identifier) REFERENCES studies (identifier)
);

CREATE TABLE study_platforms (
    study_identifier VARCHAR NOT NULL,
    ordinal INTEGER NOT NULL,
    platform_identifier VARCHAR NOT NULL,
    PRIMARY KEY (study_identifier, ordinal),
    FOREIGN KEY (study_identifier) REFERENCES studies (identifier)
);

CREATE TABLE study_publications (
    study_identifier VARCHAR NOT NULL,
    ordinal INTEGER NOT NULL,
    publication_identifier VARCHAR NOT NULL,
    PRIMARY KEY (study_identifier, ordinal),
    FOREIGN KEY (study_identifier) REFERENCES studies (identifier)
);

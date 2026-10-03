ALTER TABLE claims ADD COLUMN cell_type VARCHAR;
ALTER TABLE claims ADD COLUMN genotype VARCHAR;
ALTER TABLE claims ADD COLUMN hla_status VARCHAR;
ALTER TABLE claims ADD COLUMN allotype VARCHAR;
ALTER TABLE claims ADD COLUMN experimental_system VARCHAR;
ALTER TABLE claims ADD COLUMN endpoint VARCHAR;

CREATE TABLE study_transformations (
    study_identifier VARCHAR NOT NULL REFERENCES studies(identifier),
    ordinal INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    version VARCHAR NOT NULL,
    PRIMARY KEY (study_identifier, ordinal)
);
CREATE TABLE study_transformation_parameters (
    study_identifier VARCHAR NOT NULL,
    transformation_ordinal INTEGER NOT NULL,
    ordinal INTEGER NOT NULL,
    key VARCHAR NOT NULL,
    value VARCHAR NOT NULL,
    PRIMARY KEY (study_identifier, transformation_ordinal, ordinal),
    FOREIGN KEY (study_identifier, transformation_ordinal)
        REFERENCES study_transformations(study_identifier, ordinal)
);

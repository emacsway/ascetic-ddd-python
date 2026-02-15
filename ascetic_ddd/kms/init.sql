CREATE TABLE IF NOT EXISTS kms_keys (
    tenant_id varchar(128) NOT NULL,
    key_version integer NOT NULL,
    encrypted_key bytea NOT NULL,
    master_algorithm varchar(32) NOT NULL,
    key_algorithm varchar(32) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT %s_pk PRIMARY KEY (tenant_id, key_version)
);

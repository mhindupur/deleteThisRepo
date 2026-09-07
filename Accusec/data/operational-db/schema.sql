CREATE DATABASE IF NOT EXISTS accusec
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS accusec_test
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'accusec'@'localhost' IDENTIFIED BY 'Manju123~*';
ALTER USER 'accusec'@'localhost' IDENTIFIED BY 'Manju123~*';
GRANT ALL PRIVILEGES ON accusec.* TO 'accusec'@'localhost';
GRANT ALL PRIVILEGES ON accusec_test.* TO 'accusec'@'localhost';
FLUSH PRIVILEGES;

USE accusec;

CREATE TABLE IF NOT EXISTS entities (
  entity_id VARCHAR(255) NOT NULL PRIMARY KEY,
  provider_entity_id VARCHAR(512) NOT NULL,
  entity_type VARCHAR(128) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  workspace_id VARCHAR(64) NOT NULL,
  display_name VARCHAR(255) NOT NULL,
  account_id VARCHAR(32) NULL,
  region VARCHAR(32) NULL,
  lifecycle_state VARCHAR(32) NOT NULL,
  instance_type VARCHAR(64) NULL,
  vpc_id VARCHAR(64) NULL,
  configuration_json JSON NOT NULL,
  last_observed_at VARCHAR(64) NOT NULL,
  source VARCHAR(64) NOT NULL,
  last_sync_id VARCHAR(64) NULL,
  INDEX idx_entities_lookup (tenant_id, workspace_id, entity_type, region, instance_type),
  INDEX idx_entities_sync (provider, account_id, region, last_sync_id)
);

CREATE TABLE IF NOT EXISTS provider_connections (
  connection_id VARCHAR(64) NOT NULL PRIMARY KEY,
  provider VARCHAR(32) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  workspace_id VARCHAR(64) NOT NULL,
  account_id VARCHAR(32) NOT NULL,
  regions_json JSON NOT NULL,
  secret_ref VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL,
  last_sync_at VARCHAR(64) NULL,
  last_error VARCHAR(1024) NULL,
  created_by VARCHAR(128) NOT NULL,
  caller_arn VARCHAR(512) NULL,
  UNIQUE KEY uq_provider_account_workspace (provider, account_id, workspace_id)
);

CREATE TABLE IF NOT EXISTS sync_runs (
  sync_id VARCHAR(64) NOT NULL PRIMARY KEY,
  connection_id VARCHAR(64) NOT NULL,
  provider VARCHAR(32) NOT NULL,
  account_id VARCHAR(32) NOT NULL,
  region VARCHAR(32) NOT NULL,
  mode VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  started_at VARCHAR(64) NOT NULL,
  finished_at VARCHAR(64) NULL,
  upserted INT NOT NULL DEFAULT 0,
  missing_count INT NOT NULL DEFAULT 0,
  enumerated_types_json JSON NOT NULL,
  skipped_json JSON NOT NULL,
  error VARCHAR(1024) NULL,
  INDEX idx_sync_connection (connection_id, started_at)
);

CREATE TABLE IF NOT EXISTS entity_type_coverage (
  connection_id VARCHAR(64) NOT NULL,
  entity_type VARCHAR(128) NOT NULL,
  provider_type VARCHAR(128) NOT NULL,
  region VARCHAR(32) NOT NULL,
  depth VARCHAR(32) NOT NULL,
  resource_count INT NOT NULL DEFAULT 0,
  last_seen_at VARCHAR(64) NOT NULL,
  PRIMARY KEY (connection_id, entity_type, region)
);

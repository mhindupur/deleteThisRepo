"""Entity memory in MySQL — observations, not AWS source of truth."""

from __future__ import annotations

import json
import os
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from accusec.shared.domain.models import Entity

DDL = """
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
  INDEX idx_entities_lookup (tenant_id, workspace_id, entity_type, region, instance_type)
)
"""


def mysql_config(database: str | None = None) -> dict[str, Any]:
    return {
        "host": os.environ.get("ACCUSEC_MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("ACCUSEC_MYSQL_PORT", "3306")),
        "user": os.environ.get("ACCUSEC_MYSQL_USER", "accusec"),
        "password": os.environ.get("ACCUSEC_MYSQL_PASSWORD", "Manju123~*"),
        "database": database or os.environ.get("ACCUSEC_MYSQL_DATABASE", "accusec"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": False,
    }


def _payload_to_entity(payload: Any) -> Entity:
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode()
    if not isinstance(payload, str):
        payload = json.dumps(payload)
    return Entity.model_validate_json(payload)


class EntityStore:
    def __init__(self, database: str | None = None) -> None:
        self._cfg = mysql_config(database)
        self.database = self._cfg["database"]
        self._conn = pymysql.connect(**self._cfg)
        with self._conn.cursor() as cur:
            cur.execute(DDL)
            self._migrate(cur)
        self._conn.commit()

    def _migrate(self, cur) -> None:
        cur.execute(
            """
            SELECT COLUMN_NAME, CHARACTER_MAXIMUM_LENGTH
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'entities'
            """
        )
        cols = {row["COLUMN_NAME"]: row["CHARACTER_MAXIMUM_LENGTH"] for row in cur.fetchall()}
        if "last_sync_id" not in cols:
            cur.execute("ALTER TABLE entities ADD COLUMN last_sync_id VARCHAR(64) NULL")
        width = cols.get("provider_entity_id")
        if width is not None and int(width) < 512:
            cur.execute("ALTER TABLE entities MODIFY provider_entity_id VARCHAR(512) NOT NULL")

    def upsert(self, entity: Entity) -> None:
        cfg = dict(entity.configuration)
        sql = """
            INSERT INTO entities (
                entity_id, provider_entity_id, entity_type, provider, tenant_id,
                workspace_id, display_name, account_id, region, lifecycle_state,
                instance_type, vpc_id, configuration_json, last_observed_at, source,
                last_sync_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            ) AS new
            ON DUPLICATE KEY UPDATE
                lifecycle_state = new.lifecycle_state,
                instance_type = new.instance_type,
                vpc_id = new.vpc_id,
                configuration_json = new.configuration_json,
                last_observed_at = new.last_observed_at,
                source = new.source,
                display_name = new.display_name,
                last_sync_id = new.last_sync_id
        """
        with self._conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    entity.entity_id,
                    entity.provider_entity_id,
                    entity.entity_type,
                    entity.provider,
                    entity.tenant_id,
                    entity.workspace_id,
                    entity.display_name,
                    entity.account_id,
                    entity.region,
                    entity.lifecycle_state,
                    cfg.get("instance_type"),
                    cfg.get("vpc_id"),
                    entity.model_dump_json(),
                    entity.last_observed_at.isoformat(),
                    entity.source,
                    entity.last_sync_id,
                ),
            )
        self._conn.commit()

    def get(self, entity_id: str) -> Entity | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT configuration_json FROM entities WHERE entity_id = %s",
                (entity_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return _payload_to_entity(row["configuration_json"])

    def query(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        entity_type: str | None = None,
        region: str | None = None,
        account_id: str | None = None,
        instance_type: str | None = None,
        vpc_id: str | None = None,
        provider_entity_id: str | None = None,
        provider: str | None = None,
        lifecycle_state: str | None = None,
        exclude_missing: bool = True,
    ) -> list[Entity]:
        clauses = ["tenant_id = %s", "workspace_id = %s"]
        args: list[Any] = [tenant_id, workspace_id]
        if entity_type:
            clauses.append("entity_type = %s")
            args.append(entity_type)
        if region:
            clauses.append("LOWER(region) = LOWER(%s)")
            args.append(region)
        if account_id:
            clauses.append("account_id = %s")
            args.append(account_id)
        if instance_type:
            clauses.append("LOWER(instance_type) = LOWER(%s)")
            args.append(instance_type)
        if vpc_id:
            clauses.append("vpc_id = %s")
            args.append(vpc_id)
        if provider_entity_id:
            clauses.append("provider_entity_id = %s")
            args.append(provider_entity_id)
        if provider:
            clauses.append("provider = %s")
            args.append(provider)
        if lifecycle_state:
            clauses.append("LOWER(lifecycle_state) = LOWER(%s)")
            args.append(lifecycle_state)
        elif exclude_missing:
            clauses.append("lifecycle_state <> 'missing'")
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT configuration_json FROM entities WHERE {' AND '.join(clauses)}",
                args,
            )
            rows = cur.fetchall()
        return [_payload_to_entity(row["configuration_json"]) for row in rows]

    def mark_missing(
        self,
        *,
        provider: str,
        account_id: str,
        region: str,
        sync_id: str,
        tenant_id: str,
        workspace_id: str,
    ) -> int:
        sql = """
            UPDATE entities
            SET lifecycle_state = 'missing',
                source = source
            WHERE provider = %s
              AND account_id = %s
              AND LOWER(region) = LOWER(%s)
              AND tenant_id = %s
              AND workspace_id = %s
              AND last_sync_id IS NOT NULL
              AND last_sync_id <> %s
              AND source LIKE 'aws.%%'
              AND lifecycle_state <> 'missing'
        """
        with self._conn.cursor() as cur:
            cur.execute(sql, (provider, account_id, region, tenant_id, workspace_id, sync_id))
            count = cur.rowcount
            cur.execute(
                """
                SELECT entity_id, configuration_json FROM entities
                WHERE provider = %s AND account_id = %s AND LOWER(region) = LOWER(%s)
                  AND tenant_id = %s AND workspace_id = %s
                  AND last_sync_id IS NOT NULL AND last_sync_id <> %s
                  AND source LIKE 'aws.%%'
                """,
                (provider, account_id, region, tenant_id, workspace_id, sync_id),
            )
            rows = cur.fetchall()
            for row in rows:
                entity = _payload_to_entity(row["configuration_json"])
                entity.lifecycle_state = "missing"
                entity.freshness_status = "stale"
                cur.execute(
                    """
                    UPDATE entities SET lifecycle_state = 'missing', configuration_json = %s
                    WHERE entity_id = %s
                    """,
                    (entity.model_dump_json(), entity.entity_id),
                )
        self._conn.commit()
        return count

    def inspect_rows(self) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider_entity_id, display_name, entity_type, region,
                       instance_type, vpc_id, lifecycle_state, source, last_observed_at,
                       last_sync_id, account_id
                FROM entities
                ORDER BY region, display_name
                """
            )
            return list(cur.fetchall())
